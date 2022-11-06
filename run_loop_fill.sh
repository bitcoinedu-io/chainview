#!/bin/bash
for (( ; ; ))
do
   ./chainview_fill.py
   echo Possible crash >>log_fill.txt
   date >>log_fill.txt
   sleep 120
done

