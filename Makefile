build:
	docker build -t alert-tracker .

run:
	docker run -d --name alert-tracker-container -p 8000:5000 alert-tracker

stop:
	docker stop alert-tracker-container; docker rm alert-tracker-container; docker rmi alert-tracker

