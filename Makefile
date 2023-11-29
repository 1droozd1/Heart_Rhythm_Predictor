.PHONY: venv
.PHONY: run

venv:
	python3 -m venv venv
	./venv/bin/pip install -r requirements.txt
run:
	./venv/bin/python3 ./app/app.py