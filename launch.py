"""Frozen executable entry point; dispatches bridge, broker, MCP, or image worker."""
from lumaraw.bridge import main
if __name__ == '__main__':
    main()
