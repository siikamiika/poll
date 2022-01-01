#!/bin/bash

curl -v -d "name=testuser&create=1" -X POST 'http://localhost:8080/users'
curl -v -d "name=testusername" -X POST --cookie "token=aee99e45-1035-4ed3-bab3-a8278ca2fbde" 'http://localhost:8080/users'
curl -v -d "name=testpoll" -X POST --cookie "token=aee99e45-1035-4ed3-bab3-a8278ca2fbde" 'http://localhost:8080/polls'
curl -v -d "name=testchoice&poll_id=1" -X POST --cookie "token=aee99e45-1035-4ed3-bab3-a8278ca2fbde" 'http://localhost:8080/choices'
curl -v -d "choice_id=1" -X POST --cookie "token=aee99e45-1035-4ed3-bab3-a8278ca2fbde" 'http://localhost:8080/votes'
