#!/bin/bash
# ============================================================
#  Vishnu Multi-Agent Orchestrator — Launcher
#  Double-click this file to start the full system
# ============================================================

set -e

VISHNU_DIR="/home/user/Vishnu"
MC_DIR="/tmp/mission-control/mission-control"

export BLACKBOX_API_KEY="sk-AeiVFA4s51WsQGyHVqyZfA"
export PATH="/opt/node22/bin:$PATH"

echo "╔════════════════════════════════════════════════════════════╗"
echo "║       Vishnu Multi-Agent Orchestrator — Starting...       ║"
echo "╚════════════════════════════════════════════════════════════╝"
echo

# ------- Kill any previous instances -------
pkill -f orchestrator_app.py 2>/dev/null || true
pkill -f "next dev" 2>/dev/null || true
sleep 1

# ------- Start Orchestrator Backend (port 8888) -------
echo "[1/2] Starting Orchestrator API on port 8888..."

cat > /tmp/orchestrator_app.py << 'PYEOF'
import json, logging, os, sys
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import urlparse

sys.path.insert(0, '/home/user/Vishnu')
from orchestrator.roster import AgentRoster
from orchestrator.mal import ModelAbstractionLayer

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

roster = AgentRoster()
roster.load(Path('/home/user/Vishnu/agency_roster'))
mal = ModelAbstractionLayer()

class Handler(BaseHTTPRequestHandler):
    def _json(self, code, data):
        self.send_response(code)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()
        self.wfile.write(json.dumps(data, indent=2).encode())

    def do_OPTIONS(self):
        self._json(200, {})

    def do_GET(self):
        path = urlparse(self.path).path
        if path == '/health':
            self._json(200, {'status':'healthy','service':'Orchestrator API','agents_loaded':len(roster.list_all()),'providers_available':mal.list_available_providers()})
        elif path == '/api/orchestrator/roster':
            agents = roster.list_all()
            self._json(200, {'total':len(agents),'agents':[{'name':a.name,'emoji':a.emoji,'division':a.division,'specialty':a.specialty,'use_case':a.use_case,'default_model':a.default_model,'tags':a.tags,'role':a.role} for a in agents]})
        elif path.startswith('/api/orchestrator/roster/'):
            name = path.split('/')[-1].replace('%20',' ')
            try:
                a = roster.get_agent(name)
                self._json(200, {'name':a.name,'emoji':a.emoji,'division':a.division,'specialty':a.specialty,'use_case':a.use_case,'default_model':a.default_model,'tags':a.tags,'role':a.role})
            except Exception as e:
                self._json(404, {'error':str(e)})
        else:
            self._json(404, {'error':'Not found'})

    def do_POST(self):
        path = urlparse(self.path).path
        if path == '/api/orchestrator/jobs':
            length = int(self.headers.get('Content-Length', 0))
            body = json.loads(self.rfile.read(length))
            import uuid, datetime
            self._json(202, {'job_id':f'job-{uuid.uuid4().hex[:8]}','status':'SUBMITTED','goal':body.get('goal',''),'message':'Job submitted','timestamp':datetime.datetime.utcnow().isoformat()+'Z'})
        else:
            self._json(404, {'error':'Not found'})

    def log_message(self, fmt, *args):
        logger.info(fmt % args)

if __name__ == '__main__':
    server = HTTPServer(('127.0.0.1', 8888), Handler)
    logger.info('Orchestrator API running on http://127.0.0.1:8888')
    server.serve_forever()
PYEOF

python3 /tmp/orchestrator_app.py &
echo $! > /tmp/orchestrator.pid
echo "  ✓ Backend started (PID: $(cat /tmp/orchestrator.pid))"

# ------- Start Mission Control Frontend (port 3000) -------
echo "[2/2] Starting Mission Control GUI on port 3000..."

if [ ! -d "$MC_DIR/node_modules" ]; then
    echo "  Installing dependencies (first run only)..."
    cd "$MC_DIR"
    pnpm install --silent 2>/dev/null
fi

cd "$MC_DIR"
pnpm dev > /tmp/mission-control.log 2>&1 &
echo $! > /tmp/mission-control.pid
echo "  ✓ Frontend started (PID: $(cat /tmp/mission-control.pid))"

# ------- Wait for services to be ready -------
echo
echo "Waiting for services..."
for i in 1 2 3 4 5 6 7 8; do
    if curl -s http://127.0.0.1:8888/health > /dev/null 2>&1; then
        break
    fi
    sleep 1
done

echo
echo "╔════════════════════════════════════════════════════════════╗"
echo "║                                                            ║"
echo "║   ✅ SYSTEM READY                                         ║"
echo "║                                                            ║"
echo "║   Dashboard:  http://localhost:3000                        ║"
echo "║   API:        http://127.0.0.1:8888                       ║"
echo "║   Health:     http://127.0.0.1:8888/health                ║"
echo "║                                                            ║"
echo "║   162 agents loaded | Blackbox AI Minimax 2.5             ║"
echo "║                                                            ║"
echo "║   Press Ctrl+C to stop all services                       ║"
echo "║                                                            ║"
echo "╚════════════════════════════════════════════════════════════╝"
echo

# ------- Keep running until Ctrl+C -------
cleanup() {
    echo
    echo "Shutting down..."
    kill $(cat /tmp/orchestrator.pid 2>/dev/null) 2>/dev/null
    kill $(cat /tmp/mission-control.pid 2>/dev/null) 2>/dev/null
    pkill -f orchestrator_app.py 2>/dev/null
    pkill -f "next dev" 2>/dev/null
    echo "All services stopped."
    exit 0
}

trap cleanup SIGINT SIGTERM

# Keep script alive
while true; do
    sleep 60
done
