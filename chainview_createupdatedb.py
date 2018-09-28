#!/usr/bin/env python3
#
# chainview_createupdatedb.py
#
# Create or update chainview database based on existing version number

import sqlite3
from chainview_config import DBFILE

print('Using database file:', DBFILE)

con = sqlite3.connect(DBFILE)
c = con.cursor()
ver = '0.0'
exists = c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='version'")
if len(exists.fetchall()) > 0:
    print('Reading existing version...')
    # table exists, read version
    ver = c.execute('SELECT ver FROM version').fetchone()[0]

print('Database version:', ver)

# Note: one dummy "pending" block is special, see chainview_fill.py

if ver == '0.0':
    c.executescript("""
CREATE TABLE version (ver TEXT);

CREATE TABLE block (
    hash TEXT PRIMARY KEY,      -- 'pending' means dummy pending block
    height INTEGER UNIQUE,      -- '-1' means dummy pending block
    previousblockhash TEXT UNIQUE,
    strippedsize INTEGER,
    size INTEGER,
    weight INTEGER,
    versionhex INTEGER,
    merkleroot TEXT,
    time TEXT,
    mediantime TEXT,
    nonce INTEGER,
    bits TEXT,
    difficulty TEXT,
    chainwork TEXT,
    numtxs INTEGER
);

CREATE TABLE tx (
    txid TEXT PRIMARY KEY,
    blockhash TEXT,       -- 'pending' means in mempool only
    n INTEGER
);

CREATE TABLE input (
    txid TEXT,
    n INTEGER,
    spendstxid TEXT,
    spendsn INTEGER
);

CREATE TABLE output (
    txid TEXT,
    n INTEGER,
    type TEXT,       -- '' = normal, 'c' = nulltype/coinbase
    value INTEGER,   -- satoshis
    address TEXT
);

CREATE INDEX idx_input_txid ON input(txid);
CREATE INDEX idx_input_spendstxid ON input(spendstxid);
CREATE INDEX idx_output_txid ON output(txid);
CREATE INDEX idx_output_address ON output(address);

INSERT INTO version VALUES ('1.0');
    """)
    print ('Created database v1.0!')
else:
    print('Already up to date. Doing nothing!')
