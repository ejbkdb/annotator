#!/bin/bash
rm f2p_all.txt
rm f2p_bend.txt
rm f2p_fend.txt


files-to-prompt . --output f2p_all.txt --ignore *node_modules --ignore package-lock.json --ignore *.sh --ignore *questdb_data --ignore *dist --ignore *.csv --ignore *.db --ignore *junkfornow*
files-to-prompt ./backend --output f2p_bend.txt --ignore *node_modules --ignore package-lock.json --ignore *.sh --ignore *questdb_data --ignore *dist --ignore *.csv --ignore *.db --ignore *junkfornow*
files-to-prompt ./frontend --output f2p_fend.txt --ignore *node_modules --ignore package-lock.json --ignore *.sh --ignore *questdb_data --ignore *dist --ignore *.csv --ignore *.db --ignore *junkfornow*