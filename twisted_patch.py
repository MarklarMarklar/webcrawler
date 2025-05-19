"""
Patch for Twisted signal handling in Python 3.13+
"""

import sys
import logging

logger = logging.getLogger(__name__)

def apply_twisted_patches():
    """Apply all necessary patches for Twisted to work with Python 3.13+"""
    
    # First, ensure we're only patching when necessary
    if sys.version_info < (3, 13):
        logger.info("Running on Python version < 3.13, no patches needed")
        return
    
    logger.info("Applying Twisted compatibility patches for Python 3.13+")
    
    # Patch 1: Fix SelectReactor missing _handleSignals method
    try:
        from twisted.internet import selectreactor
        
        # If SelectReactor doesn't have _handleSignals, add a dummy implementation
        if not hasattr(selectreactor.SelectReactor, "_handleSignals"):
            logger.info("Patching SelectReactor._handleSignals")
            
            def _handle_signals_stub(self):
                """Stub implementation that does nothing"""
                pass
            
            selectreactor.SelectReactor._handleSignals = _handle_signals_stub
    except ImportError:
        logger.warning("Could not patch selectreactor, it might not be imported yet") 