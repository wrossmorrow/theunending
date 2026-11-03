#!/bin/bash
cp theunending-admin.service /etc/systemd/system/theunending-admin.service
systemctl daemon-reload
systemctl enable theunending-admin.service
systemctl start theunending-admin.service
systemctl status theunending-admin.service
