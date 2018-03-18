#!/usr/bin/env python3
#
# chainview-fill.py
#
# Fill chainview exploror sqlite3 database with blocks and transactions
# from local bitcoin node. Uses the node RPC api.

import sys
import time
import datetime
import requests
import json
import sqlite3
from chainview_config import DBFILE, URL

# Make RPC call to local node

def get(method, *args):
    headers = {'content-type': 'application/json'}
    payload = {
        "method": method,
        "params": list(args),
    }
    return requests.post(URL, data=json.dumps(payload), headers=headers).json()['result']

# Fetch one tx (used by fetchblock) and update input, output tables
# NB: uses con, cur - global variables

def fetchtx(txid):
    tx = get('getrawtransaction', txid, True)
    # fails for coinbase
    if tx:
        vins = tx['vin']
        for i,vin in enumerate(vins):
            spendstxid = vin.get('txid')
            if spendstxid:
                spendsn = vin['vout'] # prev index
                cur.execute('INSERT INTO input (txid,n,spendstxid,spendsn) VALUES (?,?,?,?)',
                            (txid, i, spendstxid, spendsn))
        vouts = tx['vout']
        for vout in vouts:
            n = vout['n']
            spb = vout['scriptPubKey']
            typ = ''
            if spb['type'] != 'nulldata':
                addr = vout['scriptPubKey']['addresses'][0]
                value = vout['value']
            else:
                addr = 'nulldata'
                value = 0
                typ = 'c'
            cur.execute('INSERT INTO output (txid,n,type,value,address) VALUES (?,?,?,?,?)',
                        (txid, n, typ, value, addr))
        

# Fetch blocks from beg to end (inclusive)
# Also, fetch all transactions included in blocks
# NB: uses con, cur - global variables
#
# TODO: check previous hash for reorders (orphans, forks)

def fetchblocks(beg, end):
    for bnum in range(beg,end + 1):
        if bnum%100 == 0:
            print(bnum, '', end='')
            sys.stdout.flush()
        hash = get('getblockhash', bnum)
        block = get('getblock', hash)
        height = block['height']
        prevhash = block.get('previousblockhash')
        if not prevhash:
            prevhash = ''
        txs = block['tx']
        # print(hash, height, prevhash)
        cur.execute('''INSERT INTO block (hash, height, previousblockhash,
        strippedsize, size, weight, versionhex, merkleroot,
        time, mediantime, nonce, bits, difficulty, chainwork, numtxs)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',
                    (hash, height, prevhash,
                     block['strippedsize'], block['size'], block['weight'],
                     block['versionHex'], block['merkleroot'],
                     block['time'], block['mediantime'], block['nonce'],
                     block['bits'], block['difficulty'], block['chainwork'],
                     str(len(block['tx']))))
        for i,tx in enumerate(block['tx']):
            cur.execute('INSERT INTO tx (txid, blockhash, n) VALUES (?,?,?)', (tx, hash, i))
            fetchtx(tx)
        con.commit()

def fetch_one_batch():
    r = cur.execute('SELECT MAX(height) FROM block')
    dbmax = r.fetchone()[0]
    if not dbmax:
        dbmax = -1

    numblocks = get('getblockchaininfo')['blocks']
    print(datetime.datetime.now().replace(microsecond=0), end=' ')
    print('Height in database: ', dbmax, ', in RPC node: ', numblocks, '. ', sep='', end='')

    beg = dbmax + 1
    end = numblocks
    # end = min(dbmax+1000, numblocks)

    if beg > end:
        print('No new blocks!')
    else:
        print('Fetching block', beg, 'to', end)
        fetchblocks(beg, end)
        print()
    
print('Using database file:', DBFILE)
con = sqlite3.connect(DBFILE)
cur = con.cursor()

while True:
    try:
        fetch_one_batch()
        time.sleep(20)
    except requests.exceptions.ConnectionError:
        print('Cannot contact node. Retry in 2 min...')
        time.sleep(120)
