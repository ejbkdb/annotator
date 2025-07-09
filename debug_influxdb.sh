#!/bin/bash

echo "=== InfluxDB Debug Information ==="
echo

echo "1. Container Status:"
docker ps -a | grep influxdb

echo
echo "2. Container Logs (last 20 lines):"
docker logs --tail 20 influxdb_annotator

echo
echo "3. Host Directory Contents:"
sudo ls -la ./influxdb_data/ 2>/dev/null || echo "Permission denied - trying with sudo failed"

echo
echo "4. Host Directory Size:"
sudo du -sh ./influxdb_data/ 2>/dev/null || echo "Permission denied - trying with sudo failed"

echo
echo "5. Container Filesystem Usage:"
docker exec influxdb_annotator df -h /var/lib/influxdb2/ 2>/dev/null || echo "Could not access container filesystem"

echo
echo "6. Container Internal Directory:"
docker exec influxdb_annotator ls -la /var/lib/influxdb2/ 2>/dev/null || echo "Could not list container directory"

echo
echo "7. InfluxDB Health Check:"
curl -s -o /dev/null -w "HTTP Status: %{http_code}\n" http://localhost:8086/ping

echo
echo "8. Available Buckets:"
curl -s -H "Authorization: Token my-super-secret-token" \
     "http://localhost:8086/api/v2/buckets?org=my-org" | \
     python3 -m json.tool 2>/dev/null || echo "Could not fetch buckets"

echo
echo "9. Docker System Info:"
docker system df

echo
echo "10. Container Resource Usage:"
docker stats --no-stream influxdb_annotator

echo
echo "=== End Debug Information ==="