.PHONY: backend-install backend-test backend-run backend-seed frontend-install frontend-build frontend-dev android-apk lint

backend-install:
	cd backend && python3 -m venv .venv && .venv/bin/pip install -r requirements.txt

backend-test:
	cd backend && (.venv/bin/pytest tests -q || python3 -m pytest tests -q || /tmp/wcm-venv/bin/python -m pytest tests -q)

backend-seed:
	cd backend && python3 seed.py

backend-run:
	cd backend && uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload

frontend-install:
	cd web && npm install

frontend-build:
	cd web && npm run build

frontend-dev:
	cd web && npm run dev

android-apk:
	cd android && ./gradlew assembleDebug

lint:
	cd backend && (ruff check app seed.py || true)
	cd web && (npm run build || true)
