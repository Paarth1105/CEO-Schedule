import os

basedir = os.path.abspath(os.path.dirname(__file__))
env_path = os.path.join(basedir, '.env')
if os.path.exists(env_path):
    try:
        with open(env_path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    k, v = line.split('=', 1)
                    os.environ[k.strip()] = v.strip().strip('"').strip("'")
    except Exception:
        pass

if not os.environ.get('DATABASE_URL'):
    os.environ['DATABASE_URL'] = 'postgresql://postgres:Software%402026@127.0.0.1:5432/ceo_schedule'

from app import app
from waitress import serve

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5005))
    print(f"Starting CEO-Schedule on Port {port}...")
    serve(app, host='0.0.0.0', port=port)