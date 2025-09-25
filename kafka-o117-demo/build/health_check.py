import sys
import os
import json
import time
from datetime import datetime

def health_check():
    try:
        current_time = datetime.now().isoformat()
        site_name = os.environ.get('SITE_NAME', 'unknown')
        
        health_status = {
            "status": "healthy",
            "timestamp": current_time,
            "site": site_name,
            "uptime": time.time()
        }
        
        print(json.dumps(health_status))
        return 0
        
    except Exception as e:
        error_status = {
            "status": "unhealthy", 
            "error": str(e),
            "timestamp": datetime.now().isoformat()
        }
        print(json.dumps(error_status))
        return 1

if __name__ == "__main__":
    sys.exit(health_check())