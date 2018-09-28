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

# Check if previous block has changed. Then a chain reordering has
# occured and some old blocks should probably be thrown away or
# database rebuilt.  Compares the topmost hash in db (dbmax) with
# previoushash in next block to fetch (beg).

def reorder_occured(dbmax, beg):
    r = cur.execute('SELECT hash FROM block WHERE height = ?', (dbmax,))
    dbhash = r.fetchone()[0]
    hash = get('getblockhash', beg)
    block = get('getblock', hash)
    prevhash = block.get('previousblockhash')
    return dbhash != prevhash, dbhash, prevhash
    
# Fetch one tx (used by fetchblock and update_pending) and update
# input, output tables
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
        return False
    else:
        clear_existing_pending()
        print('Fetching block', beg, 'to', end)
        if dbmax >= 0:
            reordered, dbhash, prevhash = reorder_occured(dbmax, beg)
            if reordered:
                print('Warning reorder detected, prevhash mismatch:', dbhash, prevhash)
                print('Delete and refill database!')
                assert(False) # automatic rewind: to be implemented
        fetchblocks(beg, end)
        return True

# Maintain a fresh copy of pending transactions in the db
# also, keep a dummy block 'pending' updated with current time

def update_pending():
    r = cur.execute('SELECT txid FROM tx WHERE blockhash = "pending"')
    existing = set([i[0] for i in r.fetchall()])
    print(existing)
    mempool = get('getrawmempool')
    size = len(mempool)
    pending = set(mempool)
    to_delete = existing - pending
    to_add = pending - existing
    print('Pending to delete:',to_delete)
    print('Pending to add:',to_add)
    delete_txids(to_delete)
    for id in to_add:
        cur.execute('INSERT INTO tx (txid, blockhash, n) VALUES (?,?,?)', (id,'pending', 0))
        fetchtx(id)
    update_pendingblock(len(pending))
    con.commit()

# Keep dummy block "pending" up to date with current time and current #pendings

def update_pendingblock(numtxs):
    currenttime = int(datetime.datetime.now().replace(microsecond=0).timestamp())
    r = cur.execute('SELECT COUNT(*) FROM block WHERE hash = "pending"')
    if int(r.fetchone()[0]) > 0:
        cur.execute('UPDATE block SET time=?, numtxs=? WHERE hash = "pending"',
                    (currenttime,numtxs))
    else:
        cur.execute('''INSERT INTO block (hash, height, previousblockhash,
        strippedsize, size, weight, versionhex, merkleroot,
        time, mediantime, nonce, bits, difficulty, chainwork, numtxs)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',
                    ('pending', -1, 'pending',
                     0, 0, 0,
                     0, 'pending',
                     currenttime, 0, 0,
                     0,0, 0,
                     numtxs))
        
# Called before adding a new block to clean up db in case any pending
# remains

def clear_existing_pending():
    r = cur.execute('SELECT txid FROM tx WHERE blockhash = "pending"')
    existing = set([i[0] for i in r.fetchall()])
    delete_txids(existing)
    con.commit()

# Small helper function, delete all transactions in 'to_delete' from
# db

def delete_txids(to_delete):
    for id in to_delete:
        cur.execute('DELETE FROM tx WHERE txid = ?', (id,))
        cur.execute('DELETE FROM input WHERE txid = ?', (id,))
        cur.execute('DELETE FROM output WHERE txid = ?', (id,))

print('Using database file:', DBFILE)
con = sqlite3.connect(DBFILE)
cur = con.cursor()

while True:
    try:
        update_pending()
        if fetch_one_batch():
            update_pending()
        time.sleep(20)
    except requests.exceptions.ConnectionError:
        print('Cannot contact node. Retry in 2 min...')
        time.sleep(120)
