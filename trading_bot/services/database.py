# trading_bot/services/database.py
from __future__ import annotations

import asyncio
from typing import Dict, List, Any, Optional
from datetime import datetime, timedelta
from motor.motor_asyncio import AsyncIOMotorClient
import pymongo

from ..config import MONGODB_URL, DATABASE_NAME, DEBUG

class DatabaseService:
    """Database service supporting both MongoDB and in-memory storage"""
    
    def __init__(self):
        self.client: Optional[AsyncIOMotorClient] = None
        self.database_name = DATABASE_NAME
        self.use_memory = False
        self._memory_trades = []
        self._memory_simulations = []
        self._initialized = False

    async def start(self):
        """Initialize database connection"""
        try:
            if MONGODB_URL and not DEBUG:
                self.client = AsyncIOMotorClient(MONGODB_URL)
                # Test connection
                await self.client.admin.command('ping')
                self.use_memory = False
                print(f"Connected to MongoDB: {DATABASE_NAME}")
            else:
                self.use_memory = True
                print("Using in-memory storage (development mode)")
        except Exception as e:
            print(f"MongoDB connection failed, falling back to memory: {e}")
            self.use_memory = True
        
        self._initialized = True

    async def stop(self):
        """Close database connection"""
        if self.client:
            self.client.close()
        self._initialized = False

    async def save_trade(self, trade: Dict[str, Any]) -> str:
        """Save trade to database"""
        trade_id = trade.get("id") or str(len(self._memory_trades) + 1)
        trade["id"] = trade_id
        trade["created_at"] = trade.get("created_at", datetime.utcnow())
        
        if self.use_memory:
            self._memory_trades.append(trade.copy())
        else:
            collection = self.client[self.database_name]["trades"]
            await collection.insert_one(trade)
        
        return trade_id

    async def fetch_recent_trades(self, limit: int = 100) -> List[Dict[str, Any]]:
        """Fetch recent trades"""
        if self.use_memory:
            return sorted(self._memory_trades, 
                         key=lambda x: x.get("created_at", datetime.min), 
                         reverse=True)[:limit]
        else:
            collection = self.client[self.database_name]["trades"]
            cursor = collection.find().sort("created_at", -1).limit(limit)
            return await cursor.to_list(length=limit)

    async def save_simulation(self, simulation: Dict[str, Any]) -> str:
        """Save simulation to database"""
        sim_id = simulation.get("simulation_id") or str(len(self._memory_simulations) + 1)
        simulation["simulation_id"] = sim_id
        simulation["created_at"] = simulation.get("created_at", datetime.utcnow())
        
        if self.use_memory:
            self._memory_simulations.append(simulation.copy())
        else:
            collection = self.client[self.database_name]["simulations"]
            await collection.insert_one(simulation)
        
        return sim_id

    async def update_simulation(self, sim_id: str, updates: Dict[str, Any]) -> bool:
        """Update simulation in database"""
        updates["updated_at"] = datetime.utcnow()
        
        if self.use_memory:
            for i, sim in enumerate(self._memory_simulations):
                if sim.get("simulation_id") == sim_id:
                    self._memory_simulations[i].update(updates)
                    return True
            return False
        else:
            collection = self.client[self.database_name]["simulations"]
            result = await collection.update_one(
                {"simulation_id": sim_id},
                {"$set": updates}
            )
            return result.modified_count > 0

    async def get_simulation(self, sim_id: str) -> Optional[Dict[str, Any]]:
        """Get simulation by ID"""
        if self.use_memory:
            for sim in self._memory_simulations:
                if sim.get("simulation_id") == sim_id:
                    return sim.copy()
            return None
        else:
            collection = self.client[self.database_name]["simulations"]
            return await collection.find_one({"simulation_id": sim_id})

# Global database instance
db = DatabaseService()
