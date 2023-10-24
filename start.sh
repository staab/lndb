#!/bin/bash

find lndb -type f | entr -r flask --app lndb.app run
