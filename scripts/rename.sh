#!/bin/bash

PREFIX="assets/img/2026-10-07-painters-block/"

BUCKET="theunending-ai-site-content-use1"
OLD_PREFIX="assets/img/2026-10-08-time-management/"
NEW_PREFIX="assets/img/2026-10-07-time-management/"

aws s3 sync "s3://${BUCKET}/${OLD_PREFIX}" "s3://${BUCKET}/${NEW_PREFIX}"
aws s3 rm "s3://${BUCKET}/${OLD_PREFIX}" --recursive
