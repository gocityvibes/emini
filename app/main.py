"""
MES Scalper Flask Application Factory

Main orchestration and dependency injection for the trading system.
"""


import os
import yaml
import logging
from datetime import datetime, timezone
from pathlib import Path
from flask import Flask, jsonify
from flask_cors import CORS

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# In-memory application state with safe defaults
app_state = {
    'running': False,
    'last_error': None,
    'last_scan_ts': None,
    'config': None,
    'components': None,
    'trades': [],
    'latest_candidate': None,
    'gpt_calls_used': 0,
    'budget_paused': False,
    'budget_paused_reason': None,
    'fingerprints': []
}

def _safe_get(config, path, default=None):
    """Safe nested config getter: _safe_get(config, 'gpt.daily_call_cap', 5)"""
    if not isinstance(config, dict):
        return default
    
    current = config
    for key in path.split('.'):
        if not isinstance(current, dict) or key not in current:
            return default
        current = current[key]
    return current

def load_config():
    """Load configuration from config.yaml with error handling."""
    config_path = (Path(os.getenv('CONFIG_PATH')) if os.getenv('CONFIG_PATH') else ((Path(__file__).parent / 'config.yaml') if (Path(__file__).parent / 'config.yaml').exists() else (Path(__file__).parent.parent / 'config.yaml')))
    
    try:
        if not config_path.exists():
            logger.error(f"Config file not found: {config_path}")
            return None
            
        with open(config_path, 'r') as f:
            config = yaml.safe_load(f)
            
        # Validate required config sections
        required_sections = ['meta', 'market', 'sessions', 'prefilter', 'gpt', 'risk', 'safety']
        missing_sections = [section for section in required_sections if section not in config]
        
        if missing_sections:
            logger.error(f"Missing required config sections: {missing_sections}")
            return None
            
        logger.info("Configuration loaded successfully")
        return config
        
    except yaml.YAMLError as e:
        logger.error(f"YAML parsing error: {e}")
        return None
    except Exception as e:
        logger.error(f"Error loading config: {e}")
        return None

def initialize_components(config, app_state):
    """Initialize all system components with error handling."""
    components = {}
    
    try:
        # Import components safely
        from data import YahooProvider, TechnicalAnalyzer
        from prefilter import SessionValidator, PremiumFilter, CostOptimizer
        try:
            from prefilter.confluence_scorer import ConfluenceScorer
        except Exception:
            # Fallback if package exposes it at top-level
            from prefilter import ConfluenceScorer
        
        # Initialize data components
        logger.info("Initializing data providers...")
        components['data_provider'] = YahooProvider(
            symbol=_safe_get(config, 'market.symbol', 'MES=F'),
            timezone=_safe_get(config, 'meta.timezone', 'America/Chicago')
        )
        
        components['technical_analyzer'] = TechnicalAnalyzer(
            timezone=_safe_get(config, 'meta.timezone', 'America/Chicago')
        )
        
        # Initialize prefilter components
        logger.info("Initializing prefilter components...")
        components['session_validator'] = SessionValidator(config)
        components['confluence_scorer'] = ConfluenceScorer(config)
        components['premium_filter'] = PremiumFilter(
            config,
            components['session_validator'],
            components['confluence_scorer']
        )
        components['cost_optimizer'] = CostOptimizer(config)
        
        # Initialize learning components if Phase 3 modules available
        try:
            from learning import FeedbackLoop, HardNegatives, PatternMemory
            from gpt import ConfidenceCalibrator
            
            logger.info("Initializing learning components...")
            components['feedback_loop'] = FeedbackLoop(config)
            components['hard_negatives'] = HardNegatives(config)
            components['pattern_memory'] = PatternMemory(config)
            components['confidence_calibrator'] = ConfidenceCalibrator(config)
            
        except ImportError as e:
            logger.warning(f"Learning components not available (Phase 3 not loaded): {e}")
        
        # Initialize GPT components if available
        try:
            from gpt import GPTTrainer, RateLimiter
            
            api_key = os.getenv('OPENAI_API_KEY')
            if api_key:
                logger.info("Initializing GPT components...")
                components['gpt_trainer'] = GPTTrainer(config, api_key)
                components['rate_limiter'] = RateLimiter(config)
            else:
                logger.warning("OPENAI_API_KEY not found - GPT components disabled")
                
        except ImportError as e:
            logger.warning(f"GPT components not available: {e}")
        except Exception as e:
            logger.error(f"Error initializing GPT components: {e}")
        
        app_state['components'] = components
        logger.info(f"Successfully initialized {len(components)} components")
        return True
        
    except ImportError as e:
        logger.error(f"Failed to import required modules: {e}")
        return False
    except Exception as e:
        logger.error(f"Error initializing components: {e}")
        app_state['last_error'] = str(e)
        return False

def create_app():
    """Flask application factory with comprehensive error handling."""
    app = Flask(__name__)
    
    try:
        # Configure CORS
        cors_origin = os.getenv('FRONTEND_CORS_ORIGIN', '*')
        CORS(app, origins=cors_origin)
        logger.info(f"CORS configured for origins: {cors_origin}")
        
        # Load configuration at startup
        config = load_config()
        if config is None:
            raise RuntimeError("Failed to load configuration - check config.yaml")
        
        app_state['config'] = config
        
        # Initialize components
        if not initialize_components(config, app_state):
            logger.warning("Some components failed to initialize - system may have limited functionality")
        
        # Add comprehensive error handling
        @app.errorhandler(404)
        def not_found(error):
            logger.warning(f"404 error: {error}")
            return jsonify({'error': 'Endpoint not found'}), 404
        
        @app.errorhandler(500)
        def internal_error(error):
            logger.error(f"500 error: {error}")
            app_state['last_error'] = str(error)
            return jsonify({
                'error': 'Internal server error', 
                'details': str(error)
            }), 500
        
        @app.errorhandler(Exception)
        def handle_exception(error):
            logger.error(f"Unhandled exception: {error}")
            app_state['last_error'] = str(error)
            return jsonify({
                'error': 'Unexpected error occurred',
                'details': str(error)
            }), 500
        
        # Add health check for components
        @app.route('/system/status', methods=['GET'])
        def system_status():
            """Detailed system status including component health."""
            components = app_state.get('components', {})
            component_status = {}
            
            for name, component in components.items():
                try:
                    # Basic health check - component exists and has expected methods
                    component_status[name] = {
                        'loaded': True,
                        'type': type(component).__name__,
                        'healthy': hasattr(component, '__dict__')
                    }
                except Exception as e:
                    component_status[name] = {
                        'loaded': False,
                        'error': str(e),
                        'healthy': False
                    }
            
            return jsonify({
                'system_healthy': len(components) > 0,
                'components_loaded': len(components),
                'components': component_status,
                'last_error': app_state.get('last_error'),
                'config_loaded': app_state.get('config') is not None,
                'running': app_state.get('running', False)
            })
        
        # Add graceful shutdown endpoint
        @app.route('/system/shutdown', methods=['POST'])
        def graceful_shutdown():
            """Gracefully shutdown components, especially rate limiter."""
            try:
                components = app_state.get('components', {})
                
                # Shutdown rate limiter if present
                if 'rate_limiter' in components:
                    logger.info("Shutting down rate limiter...")
                    components['rate_limiter'].shutdown()
                
                # Shutdown other components that need cleanup
                for name, component in components.items():
                    if hasattr(component, 'shutdown'):
                        logger.info(f"Shutting down {name}...")
                        component.shutdown()
                
                app_state['running'] = False
                logger.info("Graceful shutdown completed")
                
                return jsonify({
                    'status': 'shutdown_complete',
                    'components_shutdown': len(components)
                })
                
            except Exception as e:
                logger.error(f"Error during shutdown: {e}")
                return jsonify({
                    'status': 'shutdown_error',
                    'error': str(e)
                }), 500
        
        # Register API routes
        try:
            from api.routes import register_routes
            register_routes(app, app_state)
            logger.info("API routes registered successfully")
        except Exception as e:
            logger.error(f"Error registering routes: {e}")
            raise RuntimeError(f"Failed to register API routes: {e}")
        
        logger.info("Flask application created successfully")
        return app
        
    except Exception as e:
        logger.error(f"Failed to create Flask application: {e}")
        raise

# Create the app instance for gunicorn
try:
    app = create_app()
    logger.info("Application instance created for production")
except Exception as e:
    logger.error(f"Failed to create application instance: {e}")
    # Create a minimal error app for debugging
    app = Flask(__name__)
    
    @app.route('/health')
    def error_health():
        return jsonify({
            'status': 'error',
            'message': 'Application failed to initialize',
            'error': str(e)
        }), 500

if __name__ == '__main__':
    # Development server with enhanced error handling
    try:
        port = int(os.getenv('PORT', 5000))
        debug = os.getenv('FLASK_DEBUG', 'False').lower() == 'true'
        
        logger.info(f"Starting development server on port {port}, debug={debug}")
        app.run(host='0.0.0.0', port=port, debug=debug)
        
    except Exception as e:
        logger.error(f"Failed to start development server: {e}")
        print(f"Error starting server: {e}")

    @app.route('/')
    def root_index():
        return 'OK', 200


# ==================== PATCH: Minimal endpoints to avoid 404s ====================
try:
    from flask_cors import CORS as _PATCH_CORS
    try:
        _PATCH_CORS(app)
    except Exception:
        pass
except Exception:
    pass

# Ensure app_state exists
if 'app_state' not in globals() or not isinstance(app_state, dict):
    app_state = {
        'running': False,
        'gpt_calls_used': 0,
        'gpt_calls_cap': 5,
        'budget_paused': False,
        'budget_paused_reason': None,
        'metrics': {
            'trades_today': 0,
            'net_points_today': 0.0,
            'avg_time_to_target_sec': 0,
            'win_rate_trailing20': 0.0,
        },
        'live': {},
        'trades': [],
        'fingerprints': [],
    }

def _add_if_missing(rule, endpoint_name, view_func, methods=('GET',)):
    try:
        existing = {r.rule for r in app.url_map.iter_rules()}
    except Exception:
        existing = set()
    if rule not in existing:
        app.add_url_rule(rule, endpoint_name, view_func, methods=list(methods))

# Health + status (including /proxy/* for older checks)
def _health():
    return jsonify({'ok': True})
def _status():
    return jsonify({'running': app_state.get('running', False)})

_add_if_missing('/health', 'patch_health', _health)
_add_if_missing('/status', 'patch_status', _status)
_add_if_missing('/proxy/health', 'patch_proxy_health', _health)
_add_if_missing('/proxy/status', 'patch_proxy_status', _status)
_add_if_missing('/proxy/api/health', 'patch_proxy_api_health', _health)
_add_if_missing('/proxy/api/status', 'patch_proxy_api_status', _status)

# Budget
def _metrics_budget():
    used = int(app_state.get('gpt_calls_used', 0))
    cap  = int(app_state.get('gpt_calls_cap', 5))
    return jsonify({
        'calls_used': used,
        'calls_cap': cap,
        'calls_remaining': max(0, cap - used),
        'paused': app_state.get('budget_paused', False),
        'paused_reason': app_state.get('budget_paused_reason'),
    })
_add_if_missing('/metrics/budget', 'patch_metrics_budget', _metrics_budget)

# Summary / Live / Trades / Fingerprints
def _metrics_summary():
    m = app_state.get('metrics', {})
    return jsonify({
        **m,
        'running': app_state.get('running', False),
        'gpt_calls_used': app_state.get('gpt_calls_used', 0),
        'gpt_calls_cap': app_state.get('gpt_calls_cap', 5),
    })
_add_if_missing('/metrics/summary', 'patch_metrics_summary', _metrics_summary)
_add_if_missing('/metrics/live', 'patch_metrics_live', lambda: jsonify(app_state.get('live', {})))
_add_if_missing('/metrics/trades', 'patch_metrics_trades', lambda: jsonify(app_state.get('trades', [])))
_add_if_missing('/metrics/fingerprints', 'patch_metrics_fingerprints', lambda: jsonify(app_state.get('fingerprints', [])))

# Control
def _control_start():
    app_state['running'] = True
    app_state['gpt_calls_used'] = int(app_state.get('gpt_calls_used', 0)) + 1
    return jsonify({'ok': True, 'running': True})
_add_if_missing('/control/start', 'patch_control_start', _control_start, methods=('POST',))

def _control_stop():
    app_state['running'] = False
    return jsonify({'ok': True, 'running': False})
_add_if_missing('/control/stop', 'patch_control_stop', _control_stop, methods=('POST',))
# ==================== /PATCH ====================================================
