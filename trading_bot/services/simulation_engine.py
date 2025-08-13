# trading_bot/services/simulation_engine.py
from __future__ import annotations

import asyncio
import random
import hashlib
import uuid
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta

from ..config import (
    MODEL_NAME, HYBRID_ENABLED, HYBRID_SCORE_THRESHOLD, 
    PROMPT_UPDATE_INTERVAL, SCALP_TP_POINTS, SCALP_SL_POINTS
)
from ..models.trade import Trade, TradeDirection, TradeStatus, TradeOutcome
from ..models.simulation import Simulation, SimulationStatus
from .database import db
from .ai_service import get_trade_decision, AIDecisionError
from .ai_prefilter_service import score_setup, PrefilterError
from .outcome_logger import log_decision, log_outcome, log_prefilter
from .learning_system import update_prompt_profile

class SimulationEngine:
    """AI-powered simulation engine with GPT-5 integration"""
    
    def __init__(self):
        self.active_simulations: Dict[str, Simulation] = {}
        self.closed_trades_count = 0

    async def run_simulation_batch(self, config: Dict[str, Any]) -> Dict[str, Any]:
        """Run a batch of AI-powered simulations"""
        batch_id = str(uuid.uuid4())
        
        # Extract configuration
        total_simulations = config.get("total_simulations", 100)
        symbol = config.get("symbol", "MES")
        contract_qty = config.get("contract_qty", 1)
        allowed_directions = config.get("allowed_directions", ["long", "short"])
        profile_id = config.get("prompt_profile_id", "default")
        hybrid_enabled = config.get("hybrid_enabled", HYBRID_ENABLED)
        hybrid_threshold = config.get("hybrid_score_threshold", HYBRID_SCORE_THRESHOLD)
        
        # Run simulations
        all_trades = []
        simulation_results = []
        
        for i in range(total_simulations):
            try:
                sim_result = await self._run_single_simulation(
                    batch_id=batch_id,
                    symbol=symbol,
                    contract_qty=contract_qty,
                    allowed_directions=allowed_directions,
                    profile_id=profile_id,
                    hybrid_enabled=hybrid_enabled,
                    hybrid_threshold=hybrid_threshold
                )
                
                simulation_results.append(sim_result)
                all_trades.extend(sim_result.get("trades", []))
                
            except Exception as e:
                print(f"Simulation {i+1} failed: {e}")
                continue
        
        # Calculate batch metrics
        batch_metrics = self._calculate_batch_metrics(all_trades)
        
        return {
            "job_id": batch_id,
            "total_simulations": len(simulation_results),
            "total_trades": len(all_trades),
            "batch_metrics": batch_metrics,
            "trades": all_trades,
            "simulations": simulation_results
        }

    async def _run_single_simulation(
        self,
        batch_id: str,
        symbol: str,
        contract_qty: int,
        allowed_directions: List[str],
        profile_id: str,
        hybrid_enabled: bool,
        hybrid_threshold: float
    ) -> Dict[str, Any]:
        """Run a single AI-powered simulation"""
        
        sim_id = str(uuid.uuid4())
        simulation = Simulation(
            simulation_id=sim_id,
            batch_id=batch_id,
            market_condition="mixed",  # Will be determined by snapshots
            symbols=[symbol],
            status=SimulationStatus.RUNNING,
            start_time=datetime.utcnow()
        )
        
        self.active_simulations[sim_id] = simulation
        
        try:
            # Generate market snapshots for this simulation
            snapshots = self._generate_market_snapshots(symbol, 50)  # 50 potential trade setups
            trades = []
            
            for i, snapshot in enumerate(snapshots):
                try:
                    # Try to make an AI trade decision
                    trade = await self._process_snapshot(
                        snapshot=snapshot,
                        symbol=symbol,
                        contract_qty=contract_qty,
                        allowed_directions=allowed_directions,
                        profile_id=profile_id,
                        hybrid_enabled=hybrid_enabled,
                        hybrid_threshold=hybrid_threshold,
                        sim_id=sim_id
                    )
                    
                    if trade:
                        trades.append(trade)
                        
                        # Check if we should trigger learning update
                        if trade.status == TradeStatus.CLOSED:
                            self.closed_trades_count += 1
                            if self.closed_trades_count % PROMPT_UPDATE_INTERVAL == 0:
                                await self._trigger_learning_update(profile_id)
                
                except Exception as e:
                    print(f"Error processing snapshot {i}: {e}")
                    continue
            
            # Finalize simulation
            simulation.trades = trades
            simulation.status = SimulationStatus.COMPLETED
            simulation.end_time = datetime.utcnow()
            simulation.duration_seconds = int((simulation.end_time - simulation.start_time).total_seconds())
            simulation.metrics.calculate_metrics(trades)
            
            # Save to database
            await db.save_simulation(simulation.dict())
            
            return {
                "simulation_id": sim_id,
                "trades": [t.dict() for t in trades],
                "metrics": simulation.metrics.dict(),
                "status": "completed"
            }
            
        except Exception as e:
            simulation.status = SimulationStatus.FAILED
            simulation.error_message = str(e)
            print(f"Simulation {sim_id} failed: {e}")
            return {
                "simulation_id": sim_id,
                "trades": [],
                "status": "failed",
                "error": str(e)
            }
        
        finally:
            self.active_simulations.pop(sim_id, None)

    async def _process_snapshot(
        self,
        snapshot: Dict[str, Any],
        symbol: str,
        contract_qty: int,
        allowed_directions: List[str],
        profile_id: str,
        hybrid_enabled: bool,
        hybrid_threshold: float,
        sim_id: str
    ) -> Optional[Trade]:
        """Process a market snapshot and potentially create a trade"""
        
        snapshot_id = str(uuid.uuid4())
        snapshot_hash = hashlib.md5(str(snapshot).encode()).hexdigest()[:12]
        
        # Hybrid mode: prefilter with GPT-4.1 if enabled
        if hybrid_enabled:
            try:
                prefilter_result = score_setup(snapshot, profile_id)
                
                # Log prefilter result
                log_prefilter(
                    snapshot_meta={
                        "symbol": symbol,
                        "snapshot_id": snapshot_id,
                        "snapshot_hash": snapshot_hash,
                        "profile_id": profile_id,
                        "threshold_used": hybrid_threshold,
                        "session": snapshot.get("session", "AM"),
                        "market_condition": snapshot.get("market_condition", "mixed")
                    },
                    score_doc=prefilter_result
                )
                
                # Skip if prefilter fails
                if prefilter_result["score"] < hybrid_threshold:
                    return None
                    
            except PrefilterError as e:
                print(f"Prefilter error: {e}")
                return None
        
        # Get AI trading decision
        try:
            constraints = {"allowed_directions": allowed_directions}
            decision = get_trade_decision(snapshot, constraints, profile_id, MODEL_NAME)
            
            # Log the decision
            decision_id = log_decision({
                "symbol": symbol,
                "snapshot_id": snapshot_id,
                "snapshot_hash": snapshot_hash,
                "profile_id": profile_id,
                "model": MODEL_NAME,
                "direction": decision["direction"],
                "entry": decision["entry"],
                "sl": decision["sl"],
                "tp": decision["tp"],
                "confidence": decision["confidence"],
                "reasoning": decision["reasoning"],
                "contract_qty": contract_qty,
                "constraints": constraints,
                "policy_id": decision["policy_id"],
                "session": snapshot.get("session", "AM"),
                "market_condition": snapshot.get("market_condition", "mixed"),
                "scenario": f"sim_{sim_id}"
            })
            
            # Create and execute trade
            trade = await self._execute_simulated_trade(
                decision=decision,
                decision_id=decision_id,
                symbol=symbol,
                contract_qty=contract_qty,
                snapshot=snapshot
            )
            
            return trade
            
        except AIDecisionError as e:
            print(f"AI decision error: {e}")
            return None
        except Exception as e:
            print(f"Unexpected error in snapshot processing: {e}")
            return None

    async def _execute_simulated_trade(
        self,
        decision: Dict[str, Any],
        decision_id: str,
        symbol: str,
        contract_qty: int,
        snapshot: Dict[str, Any]
    ) -> Trade:
        """Execute a simulated trade based on AI decision"""
        
        # Create trade object
        trade = Trade(
            id=str(uuid.uuid4()),
            symbol=symbol,
            direction=TradeDirection(decision["direction"].upper()),
            entry_price=decision["entry"],
            stop_loss=decision["sl"],
            take_profit=decision["tp"],
            quantity=contract_qty,
            contract_qty=contract_qty,
            status=TradeStatus.ACTIVE,
            entry_time=datetime.utcnow(),
            confidence=decision["confidence"],
            reasoning=decision["reasoning"]
        )
        
        # Simulate trade execution with realistic fills
        exit_price, duration_s, hit_target = self._simulate_trade_outcome(
            entry=decision["entry"],
            sl=decision["sl"],
            tp=decision["tp"],
            direction=decision["direction"],
            market_data=snapshot
        )
        
        # Close the trade
        trade.exit_price = exit_price
        trade.exit_time = datetime.utcnow() + timedelta(seconds=duration_s)
        trade.status = TradeStatus.CLOSED
        trade.time_to_target_sec = duration_s
        
        # Calculate outcome
        if trade.direction == TradeDirection.LONG:
            pnl_ticks = exit_price - trade.entry_price
        else:
            pnl_ticks = trade.entry_price - exit_price
        
        trade.pnl = pnl_ticks
        trade.pnl_usd = pnl_ticks * 5.0 * contract_qty  # MES: $5 per tick
        
        if abs(pnl_ticks) < 0.01:  # Essentially breakeven
            trade.outcome = TradeOutcome.BREAKEVEN
            result = "be"
        elif pnl_ticks > 0:
            trade.outcome = TradeOutcome.WIN
            result = "win"
        else:
            trade.outcome = TradeOutcome.LOSS
            result = "loss"
        
        # Log the outcome
        log_outcome({
            "decision_id": decision_id,
            "exit": exit_price,
            "pnl_ticks": pnl_ticks,
            "pnl_usd": trade.pnl_usd,
            "duration_s": duration_s,
            "result": result,
            "slipped_ticks": 0,  # No slippage in simulation
            "hit_target": hit_target,
            "mae_ticks": 0,  # Simplified for now
            "mfe_ticks": abs(pnl_ticks) if pnl_ticks > 0 else 0
        })
        
        # Save trade to database
        await db.save_trade(trade.dict())
        
        return trade

    def _simulate_trade_outcome(
        self,
        entry: float,
        sl: float,
        tp: float,
        direction: str,
        market_data: Dict[str, Any]
    ) -> tuple[float, int, bool]:
        """Simulate realistic trade outcome"""
        
        # Get market characteristics
        volatility = market_data.get("volatility", 0.02)
        trend_strength = market_data.get("trend_strength", 0.0)
        momentum = market_data.get("momentum", "neutral")
        
        # Simulate win/loss probability based on market conditions
        base_win_rate = 0.65  # Base scalping win rate
        
        # Adjust for market conditions
        if momentum == "strong" and abs(trend_strength) > 0.5:
            win_rate = base_win_rate + 0.1
        elif momentum == "weak" or abs(trend_strength) < 0.2:
            win_rate = base_win_rate - 0.1
        else:
            win_rate = base_win_rate
        
        # Adjust for direction alignment
        if direction == "long" and trend_strength > 0:
            win_rate += 0.05
        elif direction == "short" and trend_strength < 0:
            win_rate += 0.05
        
        # Simulate outcome
        hit_target = random.random() < win_rate
        
        if hit_target:
            exit_price = tp
            # Faster fills on targets (30-120 seconds)
            duration_s = random.randint(30, 120)
        else:
            exit_price = sl
            # Slower fills on stops (60-300 seconds)
            duration_s = random.randint(60, 300)
        
        return exit_price, duration_s, hit_target

    def _generate_market_snapshots(self, symbol: str, count: int) -> List[Dict[str, Any]]:
        """Generate realistic market snapshots for testing"""
        snapshots = []
        base_price = 5100.0  # MES base price
        
        for i in range(count):
            # Random walk with trend
            price_change = random.gauss(0, 2.0)  # 2-point standard deviation
            current_price = base_price + price_change
            
            # Market condition
            volatility = random.uniform(0.01, 0.04)
            trend_strength = random.uniform(-0.8, 0.8)
            
            momentum = "strong" if abs(trend_strength) > 0.5 else \
                      "weak" if abs(trend_strength) < 0.2 else "neutral"
            
            # Session (simplified)
            session = "AM" if i % 3 == 0 else "PM"
            
            snapshot = {
                "timestamp": datetime.utcnow(),
                "symbol": symbol,
                "current_price": current_price,
                "volatility": volatility,
                "trend_strength": trend_strength,
                "momentum": momentum,
                "session": session,
                "volume": random.choice(["low", "normal", "high"]),
                "market_condition": "trend" if abs(trend_strength) > 0.4 else "chop",
                "range_3bars": random.uniform(1.0, 4.0),
                "rsi": random.uniform(30, 70),
                "above_sma20": trend_strength > 0,
                "below_sma20": trend_strength < 0
            }
            
            snapshots.append(snapshot)
        
        return snapshots

    async def _trigger_learning_update(self, profile_id: str):
        """Trigger learning system update"""
        try:
            await update_prompt_profile(profile_id)
            print(f"Learning update triggered for profile: {profile_id}")
        except Exception as e:
            print(f"Learning update failed: {e}")

    def _calculate_batch_metrics(self, trades: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Calculate metrics for the entire batch"""
        if not trades:
            return {"total_trades": 0, "win_rate": 0.0, "total_pnl": 0.0}
        
        total_trades = len(trades)
        wins = len([t for t in trades if t.get("pnl", 0) > 0])
        total_pnl = sum(t.get("pnl", 0) for t in trades)
        total_pnl_usd = sum(t.get("pnl_usd", 0) for t in trades)
        
        return {
            "total_trades": total_trades,
            "win_rate": wins / total_trades if total_trades > 0 else 0.0,
            "total_pnl": total_pnl,
            "total_pnl_usd": total_pnl_usd,
            "average_pnl": total_pnl / total_trades if total_trades > 0 else 0.0
        }

# Global simulation engine instance
simulation_engine = SimulationEngine()

# Backward compatibility function
async def run_simulation_batch(config: Dict[str, Any]) -> Dict[str, Any]:
    """Run simulation batch - backward compatibility"""
    return await simulation_engine.run_simulation_batch(config)
