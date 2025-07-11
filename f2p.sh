#!/bin/bash
rm t.txt
files-to-prompt . --output t.txt --ignore *node_modules --ignore package-lock.json --ignore *.sh