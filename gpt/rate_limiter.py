"""
GPT Rate Limiter
Controls and serializes GPT API calls with daily limits and pause enforcement.
"""

import asyncio
import threading
from datetime import datetime, timezone
from typing import Dict, Optional, List, Callable
from dataclasses import dataclass
from queue import Queue, Empty
from enum import Enum


class RequestStatus(Enum):
    """GPT request status."""
    PENDING = "pending"
    PROCESSING = "processing" 
    COMPLETED = "completed"
    FAILED = "failed"
    REJECTED = "rejected"


@dataclass
class GPTRequest:
    """GPT API request object."""
    request_id: str
    candidate_data: Dict
    timestamp: datetime
    priority: int  # Higher number = higher priority
    callback: Optional[Callable] = None
    status: RequestStatus = RequestStatus.PENDING
    result: Optional[Dict] = None
    error: Optional[str] = None
    processing_time_ms: int = 0


class RateLimiter:
    """
    GPT API rate limiter with daily caps and pause enforcement.
    
    Features:
    - Daily call cap enforcement (≤5 calls)
    - Request serialization (no concurrent calls)
    - Pause state enforcement from cost optimizer
    - Request queuing with priority
    - Usage tracking and reporting
    """
    
    def __init__(self, config: Dict):
        """
        Initialize rate limiter.
        
        Args:
            config: System configuration with GPT settings
        """
        self.config = config
        self.daily_cap = config['gpt']['daily_call_cap']
        
        # State tracking
        self.calls_used_today = 0
        self.last_reset_date = datetime.now(timezone.utc).date()
        self.is_paused = False
        self.pause_reason = None
        
        # Request management
        self.request_queue = Queue()
        self.active_request = None
        self.completed_requests = []
        
        # Thread safety
        self.lock = threading.Lock()
        self.processing_thread = None
        self.shutdown_event = threading.Event()
        
        # Start processing thread
        self._start_processing_thread()
    
    def submit_request(self, candidate_data: Dict, priority: int = 1) -> str:
        """
        Submit GPT request for processing.
        
        Args:
            candidate_data: Candidate information for GPT
            priority: Request priority (higher = more urgent)
            
        Returns:
            Request ID for tracking
        """
        with self.lock:
            # Check daily reset
            self._check_daily_reset()
            
            # Generate request ID
            request_id = f"gpt_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}"
            
            # Create request object
            request = GPTRequest(
                request_id=request_id,
                candidate_data=candidate_data,
                timestamp=datetime.now(timezone.utc),
                priority=priority
            )
            
            # Check if request can be accepted
            if self._can_accept_request():
                self.request_queue.put(request)
                return request_id
            else:
                # Reject request
                request.status = RequestStatus.REJECTED
                request.error = self._get_rejection_reason()
                self.completed_requests.append(request)
                return request_id
    
    def _can_accept_request(self) -> bool:
        """Check if new requests can be accepted."""
        return (
            not self.is_paused and 
            self.calls_used_today < self.daily_cap and
            not self.shutdown_event.is_set()
        )
    
    def _get_rejection_reason(self) -> str:
        """Get reason for request rejection."""
        if self.is_paused:
            return f"Rate limiter paused: {self.pause_reason}"
        elif self.calls_used_today >= self.daily_cap:
            return f"Daily cap reached: {self.calls_used_today}/{self.daily_cap}"
        else:
            return "System shutdown"
    
    def set_pause_state(self, paused: bool, reason: Optional[str] = None):
        """
        Set pause state (called by cost optimizer).
        
        Args:
            paused: True to pause, False to resume
            reason: Reason for pause
        """
        with self.lock:
            self.is_paused = paused
            self.pause_reason = reason if paused else None
    
    def get_request_status(self, request_id: str) -> Optional[GPTRequest]:
        """
        Get status of specific request.
        
        Args:
            request_id: Request ID to check
            
        Returns:
            GPTRequest object or None if not found
        """
        with self.lock:
            # Check active request
            if self.active_request and self.active_request.request_id == request_id:
                return self.active_request
            
            # Check completed requests
            for request in self.completed_requests:
                if request.request_id == request_id:
                    return request
            
            # Check queue (convert to list to search)
            queue_items = []
            try:
                while True:
                    item = self.request_queue.get_nowait()
                    queue_items.append(item)
                    if item.request_id == request_id:
                        found_request = item
                        break
            except Empty:
                found_request = None
            
            # Put items back in queue
            for item in reversed(queue_items):
                self.request_queue.put(item)
            
            return found_request
    
    def get_usage_counters(self) -> Dict[str, int]:
        """
        Get current usage counters.
        
        Returns:
            Dict with usage statistics
        """
        with self.lock:
            self._check_daily_reset()
            
            return {
                'calls_used': self.calls_used_today,
                'calls_cap': self.daily_cap,
                'calls_remaining': max(0, self.daily_cap - self.calls_used_today),
                'requests_queued': self.request_queue.qsize(),
                'requests_completed_today': len([
                    r for r in self.completed_requests 
                    if r.timestamp.date() == datetime.now(timezone.utc).date()
                ]),
                'is_paused': self.is_paused,
                'active_request_id': self.active_request.request_id if self.active_request else None
            }
    
    def _start_processing_thread(self):
        """Start background thread for processing requests."""
        if self.processing_thread is None or not self.processing_thread.is_alive():
            self.processing_thread = threading.Thread(
                target=self._process_requests,
                daemon=True,
                name="GPTRateLimiter"
            )
            self.processing_thread.start()
    
    def _process_requests(self):
        """Main processing loop (runs in background thread)."""
        from .trainer import GPTTrainer  # Import here to avoid circular imports
        
        # Initialize GPT trainer
        try:
            import os
            api_key = os.getenv('OPENAI_API_KEY')
            if not api_key:
                print("ERROR: OPENAI_API_KEY not found")
                return
            
            trainer = GPTTrainer(self.config, api_key)
        except Exception as e:
            print(f"ERROR: Failed to initialize GPT trainer: {e}")
            return
        
        while not self.shutdown_event.is_set():
            try:
                # Get next request (blocks until available)
                request = self.request_queue.get(timeout=1.0)
                
                with self.lock:
                    # Final check before processing
                    if not self._can_accept_request():
                        request.status = RequestStatus.REJECTED
                        request.error = self._get_rejection_reason()
                        self.completed_requests.append(request)
                        continue
                    
                    # Mark as active
                    self.active_request = request
                    request.status = RequestStatus.PROCESSING
                
                # Process request (outside lock to avoid blocking)
                start_time = datetime.now()
                
                try:
                    # Call GPT trainer
                    gpt_decision = trainer.evaluate_candidate(request.candidate_data)
                    
                    # Record success
                    with self.lock:
                        self.calls_used_today += 1
                        request.status = RequestStatus.COMPLETED
                        request.result = {
                            'decision': gpt_decision.decision,
                            'direction': gpt_decision.direction,
                            'named_setup': gpt_decision.named_setup,
                            'confluences': gpt_decision.confluences,
                            'confidence': gpt_decision.confidence,
                            'rationale': gpt_decision.rationale,
                            'processing_time_ms': gpt_decision.processing_time_ms
                        }
                        request.processing_time_ms = int((datetime.now() - start_time).total_seconds() * 1000)
                        
                except Exception as e:
                    # Record failure
                    with self.lock:
                        request.status = RequestStatus.FAILED
                        request.error = str(e)
                        request.processing_time_ms = int((datetime.now() - start_time).total_seconds() * 1000)
                
                # Move to completed list
                with self.lock:
                    self.completed_requests.append(request)
                    self.active_request = None
                    
                    # Limit completed list size
                    if len(self.completed_requests) > 100:
                        self.completed_requests = self.completed_requests[-50:]
                
                # Execute callback if provided
                if request.callback:
                    try:
                        request.callback(request)
                    except Exception as e:
                        print(f"Callback error for request {request.request_id}: {e}")
                
            except Empty:
                # Timeout waiting for request - continue loop
                continue
            except Exception as e:
                print(f"Processing error: {e}")
                continue
    
    def _check_daily_reset(self):
        """Reset daily counters if new day."""
        current_date = datetime.now(timezone.utc).date()
        
        if current_date > self.last_reset_date:
            self.calls_used_today = 0
            self.last_reset_date = current_date
            
            # Auto-resume if paused due to daily cap
            if self.pause_reason == "daily_cap_reached":
                self.is_paused = False
                self.pause_reason = None
    
    def get_recent_requests(self, limit: int = 10) -> List[Dict]:
        """
        Get recent requests for monitoring.
        
        Args:
            limit: Maximum number of requests to return
            
        Returns:
            List of request summaries
        """
        with self.lock:
            recent = self.completed_requests[-limit:] if self.completed_requests else []
            
            summaries = []
            for request in reversed(recent):  # Most recent first
                summary = {
                    'request_id': request.request_id,
                    'timestamp': request.timestamp.isoformat(),
                    'status': request.status.value,
                    'processing_time_ms': request.processing_time_ms,
                    'setup_type': request.candidate_data.get('candidate', {}).get('setup_type', 'unknown')
                }
                
                if request.status == RequestStatus.COMPLETED and request.result:
                    summary['decision'] = request.result.get('decision')
                    summary['confidence'] = request.result.get('confidence')
                elif request.status in [RequestStatus.FAILED, RequestStatus.REJECTED]:
                    summary['error'] = request.error
                
                summaries.append(summary)
            
            return summaries
    
    def get_performance_stats(self) -> Dict:
        """
        Get performance statistics for rate limiting.
        
        Returns:
            Dict with performance metrics
        """
        with self.lock:
            if not self.completed_requests:
                return {'status': 'no_data'}
            
            # Filter today's requests
            today = datetime.now(timezone.utc).date()
            today_requests = [r for r in self.completed_requests if r.timestamp.date() == today]
            
            if not today_requests:
                return {'status': 'no_data_today'}
            
            # Calculate stats
            successful = [r for r in today_requests if r.status == RequestStatus.COMPLETED]
            failed = [r for r in today_requests if r.status == RequestStatus.FAILED]
            rejected = [r for r in today_requests if r.status == RequestStatus.REJECTED]
            
            # Processing time stats
            processing_times = [r.processing_time_ms for r in successful if r.processing_time_ms > 0]
            
            stats = {
                'status': 'data_available',
                'total_requests': len(today_requests),
                'successful': len(successful),
                'failed': len(failed),
                'rejected': len(rejected),
                'success_rate': (len(successful) / len(today_requests)) * 100 if today_requests else 0
            }
            
            if processing_times:
                stats['avg_processing_time_ms'] = sum(processing_times) / len(processing_times)
                stats['min_processing_time_ms'] = min(processing_times)
                stats['max_processing_time_ms'] = max(processing_times)
            
            return stats
    
    def clear_completed_requests(self):
        """Clear completed requests (admin function)."""
        with self.lock:
            self.completed_requests.clear()
    
    def shutdown(self):
        """Shutdown rate limiter and stop processing."""
        self.shutdown_event.set()
        
        if self.processing_thread and self.processing_thread.is_alive():
            self.processing_thread.join(timeout=5.0)
    
    def force_process_queue(self) -> int:
        """
        Force process all queued requests (admin override).
        
        Returns:
            Number of requests processed
        """
        processed = 0
        
        while not self.request_queue.empty():
            try:
                request = self.request_queue.get_nowait()
                
                # Mark as rejected due to force clear
                request.status = RequestStatus.REJECTED
                request.error = "Force cleared by admin"
                
                with self.lock:
                    self.completed_requests.append(request)
                
                processed += 1
                
            except Empty:
                break
        
        return processed
    
    def get_system_status(self) -> Dict:
        """
        Get comprehensive system status.
        
        Returns:
            Dict with complete status information
        """
        with self.lock:
            self._check_daily_reset()
            
            return {
                'rate_limiter': {
                    'calls_used': self.calls_used_today,
                    'calls_cap': self.daily_cap,
                    'calls_remaining': max(0, self.daily_cap - self.calls_used_today),
                    'is_paused': self.is_paused,
                    'pause_reason': self.pause_reason,
                    'last_reset_date': self.last_reset_date.isoformat()
                },
                'queue': {
                    'pending_requests': self.request_queue.qsize(),
                    'active_request': self.active_request.request_id if self.active_request else None,
                    'completed_requests': len(self.completed_requests)
                },
                'processing': {
                    'thread_alive': self.processing_thread.is_alive() if self.processing_thread else False,
                    'shutdown_requested': self.shutdown_event.is_set()
                },
                'performance': self.get_performance_stats()
            }


# Rate limiting policies and usage:
"""
Daily Cap Enforcement:
- Hard limit: ≤5 GPT calls per day
- Automatic rejection when cap reached
- Daily reset at midnight UTC
- Auto-resume after reset

Request Serialization:
- Only one GPT call processed at a time
- Requests queued in submission order
- Priority field available for future use
- Background thread handles processing

Pause Enforcement:
- Controlled by CostOptimizer
- Immediate effect on new requests
- Active request allowed to complete
- Queued requests remain pending

Usage Example:
```python
rate_limiter = RateLimiter(config)

# Submit request
request_id = rate_limiter.submit_request(candidate_data, priority=1)

# Check status
request = rate_limiter.get_request_status(request_id)
if request.status == RequestStatus.COMPLETED:
    decision = request.result['decision']
    confidence = request.result['confidence']

# Get usage stats
counters = rate_limiter.get_usage_counters()
print(f"Used: {counters['calls_used']}/{counters['calls_cap']}")
```

Request Flow:
1. submit_request() → validate → queue
2. Background thread → dequeue → process → complete
3. get_request_status() → check result
4. Callback executed if provided

Error Handling:
- API failures → RequestStatus.FAILED
- Rate limit hits → RequestStatus.REJECTED  
- Pause state → RequestStatus.REJECTED
- Processing errors → logged and continued

Performance Monitoring:
- Processing time tracking
- Success/failure rates
- Queue depth monitoring
- Daily usage reporting

System Status Output:
{
    'rate_limiter': {
        'calls_used': 3,
        'calls_cap': 5,
        'calls_remaining': 2,
        'is_paused': false,
        'pause_reason': null
    },
    'queue': {
        'pending_requests': 1,
        'active_request': 'gpt_20250120_143045_123456',
        'completed_requests': 15
    },
    'performance': {
        'success_rate': 95.2,
        'avg_processing_time_ms': 1850
    }
}
"""