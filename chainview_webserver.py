#!/usr/bin/env python3

# Run via flask framework:
# pip3 install flask
# FLASK_APP=chainview-webserver.py flask run

import sys
import requests, json
import datetime, time
import decimal
import sqlite3
from flask import Flask, url_for, abort, request, redirect
from flask import render_template
from chainview_config import VERSION, GITHUB, DBFILE, chaininfo, params

app = Flask(__name__)

# Round bitcoin amounts to 8 decimals (satoshis)
# only needed once when going from float values
def float2dec(a):
    a = decimal.Decimal(a)
    return a.quantize(decimal.Decimal(10)**-8)

# decimal/float to string, remove trailing 0 and maybe '.'
def num2str(d):
    return ('%.8f' % float(d)).rstrip('0').rstrip('.')

# Calc now - time and express rounded in human language
# time, now should be datetime objects

def ageof(time, now):
    delta = now - time
    d = delta.days
    h = delta.seconds // 3600
    m = (delta.seconds // 60) % 60
    s = delta.seconds % 60
    age = ''
    if d > 0:
        age += '%d days %d hours' % (d,h)
    else:
        if h > 0:
            age += '%d hours %d min' % (h,m)
        else:
            age += '%d min %d sec' % (m,s)
    return age

# Given db cursor cur, fetch info to display on top

def latest_topinfo(cur):
    r = cur.execute('SELECT MAX(height) FROM block')
    dbmax = r.fetchone()[0]
    timestamp = 0
    if not dbmax:
        dbmax = -1
    else:
        r = cur.execute('SELECT time FROM block WHERE height = ?', (dbmax,))
        timestamp = r.fetchone()[0]
    now = datetime.datetime.now().replace(microsecond=0)
    timelast = datetime.datetime.fromtimestamp(int(timestamp))
    age = ageof(timelast, now)
    is_dst = time.daylight and time.localtime().tm_isdst > 0
    tzname = time.tzname[is_dst]
    nowstr = now.strftime('%a') + ' ' + str(now) + ' ' + tzname
    r = cur.execute('SELECT COUNT(*) FROM tx WHERE blockhash="pending"')
    pending = int(r.fetchone()[0])
    return {'dbmax': dbmax, 'time': timelast, 'age': age, 'now': now, 'nowstr': nowstr,
            'pending': pending,
            'version': VERSION, 'github': GITHUB}

############## main page is same as block list page
# startblock is the highest block number to display at the top

BLOCKS_PER_PAGE = 500

@app.route("/<int:startblock>")
@app.route("/blocks/<int:startblock>")
@app.route("/")
@app.route("/blocks/")
def main_page(startblock=None):
    con = sqlite3.connect(DBFILE)
    cur = con.cursor()
    topinfo = latest_topinfo(cur)
    dbmax = topinfo['dbmax']
    now = topinfo['now']

    if startblock == None:
        high = dbmax
    else:
        high = max(min(int(startblock), dbmax), 0)
    low = max(high - BLOCKS_PER_PAGE + 1, 0)
    
    prevpage = max(high - BLOCKS_PER_PAGE, BLOCKS_PER_PAGE - 1)
    nextpage = min(high + BLOCKS_PER_PAGE, dbmax)
    prevurl = url_for('main_page', startblock=prevpage) if prevpage < high else ''
    nexturl = url_for('main_page', startblock=nextpage) if nextpage > high else ''

    # extra option to only show blocks with #txs > txlimit (to get rid of empty blocks)
    # (todo: next/prev doesn't really work properly when using txlimit)
    txlimit = int(request.args.get('txlimit','0'))
    
    r = cur.execute('''
        SELECT height, time, numtxs FROM block
        WHERE height <= ? AND height >= 0 AND numtxs >= ?
        ORDER BY height DESC LIMIT ?''', (str(high),txlimit,BLOCKS_PER_PAGE))
    blocks = []
    for r in r.fetchall():
        time = datetime.datetime.fromtimestamp(int(r[1]))
        b = {'height': r[0], 'time': time, 'age': ageof(time,now), 'numtxs': r[2]}
        blocks.append(b)
    info = {'low': low, 'high': high, 'prevurl': prevurl, 'nexturl': nexturl}
    if startblock == None:
        pagetitle = 'Latest blocks'
    else:
        pagetitle = 'Blocks %d to %d' % (low, high)
        
    return render_template('main-page.html', pagetitle=pagetitle, chaininfo=chaininfo, topinfo=topinfo,
                           info=info, blocks=blocks)

# Helper for block_page, address_page, and block_pending
# For each transaction in txs, fetch inputs and outputs
# For an input, fetch corresponding spent output address and value
# For an output, also find txid if spent in later transaction
# Note: adds data to existing txs elements

def get_inputs_outputs(txs, cur):
    for tx in txs:
        txid = tx['txid']
        resI = cur.execute('SELECT output.address, output.value FROM input INNER JOIN output ON input.spendstxid=output.txid AND input.spendsn=output.n WHERE input.txid = ? ORDER BY input.n',
                           (txid,))
        inputs = resI.fetchall()
        if len(inputs) == 0:
            tx['inputs'] = [('Coinbase', 'mining reward')]
        else:
            tx['inputs'] = [(i[0], num2str(i[1])) for i in inputs]
        resO = cur.execute(
            '''SELECT output.address,output.value,output.type,input.txid FROM output
               LEFT JOIN input ON input.spendstxid=output.txid AND input.spendsn=output.n
               WHERE output.txid=? ORDER BY output.n''', (txid,))
        tx['outputs'] = [{'address':r[0], 'value':num2str(r[1]), 'type':r[2], 'spentby':r[3]}
                         for r in resO.fetchall()]
        if tx['inputs'][0][0] != 'Coinbase':
            fee = decimal.Decimal('0.0')
            for ip in tx['inputs']:
                fee += float2dec(ip[1])
            for op in tx['outputs']:
                fee -= float2dec(op['value'])
            tx['fee'] = num2str(fee)
    return

@app.route("/block/<int:blocknr>")
def block_page(blocknr):
    con = sqlite3.connect(DBFILE)
    cur = con.cursor()
    topinfo = latest_topinfo(cur)
    now = topinfo['now']
    
    r = cur.execute('''SELECT height, hash, previousblockhash, merkleroot, time, difficulty, numtxs
                          FROM block WHERE height = ?''',
                    (blocknr,))
    r = r.fetchone()
    if r:
        timestamp = int(r[4])
        time = datetime.datetime.fromtimestamp(timestamp)
        age = ageof(time, now)
        block = {'height': r[0], 'hash': r[1], 'prevhash': r[2], 'merkle': r[3],
                 'time': time, 'age': age, 'diff': r[5], 'numtxs': r[6]}
        prevb = blocknr - 1
        if prevb < 0:
            prevb = 0
        nextb = blocknr + 1
        if nextb > topinfo['dbmax']:
            nextb = topinfo['dbmax']
        prevurl = url_for('block_page', blocknr=prevb) if prevb < blocknr else ''
        nexturl = url_for('block_page', blocknr=nextb) if nextb > blocknr else ''
        info = {'prevurl': prevurl, 'nexturl': nexturl}
        res = cur.execute('SELECT txid,n FROM tx WHERE blockhash = ? ORDER BY n', (block['hash'],))
        txs = [{'txid':r[0], 'n':r[1]} for r in res.fetchall()]
        txinfo = {'page':'block', 'header':''}
        get_inputs_outputs(txs, cur)
        return render_template('block-page.html', chaininfo=chaininfo, topinfo=topinfo, info=info,
                               block=block, txinfo=txinfo, txs=txs)
    else:
    	return render_template('searchfail-page.html', chaininfo=chaininfo, topinfo=topinfo, search=blocknr, err='Cannot find block!')

@app.route("/block/pending")
def block_pending():
    con = sqlite3.connect(DBFILE)
    cur = con.cursor()
    topinfo = latest_topinfo(cur)
    now = topinfo['now']
    
    res = cur.execute('SELECT txid,n FROM tx WHERE blockhash = ? ORDER BY n', ('pending',))
    txs = [{'txid':r[0], 'n':r[1]} for r in res.fetchall()]
    txinfo = {'page':'block', 'header':''}
    get_inputs_outputs(txs, cur)
    return render_template('block-pending.html', chaininfo=chaininfo, topinfo=topinfo,
                           txinfo=txinfo, txs=txs)
    
@app.route("/address/<address>")
def address_page(address):
    con = sqlite3.connect(DBFILE)
    cur = con.cursor()
    topinfo = latest_topinfo(cur)
    now = topinfo['now']

    # Search for address in both outputs and inputs
    res = cur.execute('''
       SELECT txid,block.height,block.time FROM
       (SELECT output.txid as id FROM output
               WHERE output.address=?
       UNION
       SELECT input.txid as id FROM output
               JOIN input ON input.spendstxid=output.txid AND input.spendsn=output.n
               WHERE output.address=?)
       JOIN tx ON tx.txid=id
       JOIN block ON tx.blockhash=block.hash
       ORDER BY block.height DESC, tx.n DESC
    ''', (address, address))

    txs = [{'txid':r[0], 'n':-1, 'height':r[1], 'time':datetime.datetime.fromtimestamp(int(r[2]))}
           for r in res.fetchall()]
    if len(txs) == 0:
    	return render_template('searchfail-page.html', chaininfo=chaininfo, topinfo=topinfo, search=address, err='Cannot find address (no transactions found)!')

    get_inputs_outputs(txs, cur)
    
    balance = decimal.Decimal('0.0')
    for tx in txs:
        for op in tx['outputs']:
            if op['address'] == address and not op['spentby']:
                balance += float2dec(op['value'])
        
    # split off pending txs if any
    pendingtxs = []
    i = 0
    while i < len(txs):
        tx = txs[i]
        if tx['height'] == -1:
            ptx = txs.pop(i)
            pendingtxs.append(ptx)
        else:
            i += 1

    firstuse = txs[-1]['time']
    lastuse  = txs[0]['time']
    if len(pendingtxs) > 0:
        lastuse = pendingtxs[0]['time']
    agefirst = ageof(firstuse, now)
    agelast = ageof(lastuse, now)
    addr = {'addr':address, 'balance':num2str(balance),
            'firstuse':firstuse, 'agefirst':agefirst,
            'lastuse':lastuse, 'agelast':agelast,
            'notxs':len(txs)+len(pendingtxs)}
    txinfo = {'page':'address', 'header':', recent first'}
    
    # extra option to remove coinbase-txs
    nocb = int(request.args.get('nocb','0'))
    if nocb:
        txs = list(filter(lambda tx: tx['inputs'][0][0] != 'Coinbase', txs))
        txinfo['header'] += ', no coinbase (%i txs)' % len(txs)
        
    limit = 500
    if len(txs) > limit:
        txs = txs[0:500] # limit html to last txs
        txinfo['header'] += ', showing only 500'
    return render_template('address-page.html', chaininfo=chaininfo, topinfo=topinfo,
                           addr=addr, txinfo=txinfo, pendingtxs=pendingtxs, ctxs=txs)

@app.route("/stats/")
def stats_page():
    con = sqlite3.connect(DBFILE)
    cur = con.cursor()
    topinfo = latest_topinfo(cur)
    now = topinfo['now']
    dbmax = topinfo['dbmax']
    res = cur.execute('SELECT address, value FROM output JOIN tx ON output.txid=tx.txid WHERE tx.n="0" and output.n="0"')
    topminers = {}
    for r in res.fetchall():
        addr = r[0]
        value = r[1]
        if addr in topminers:
            topminers[addr] += decimal.Decimal(value)
        else:
            topminers[addr] = decimal.Decimal(value)
        topminers[addr] = topminers[addr].quantize(decimal.Decimal(10)**-8)
    topminers = sorted(topminers.items(), key=lambda i: (-i[1],i))

    res = cur.execute('SELECT time,difficulty FROM block WHERE height=?', (dbmax,))
    time0, diff0 = res.fetchone()
    dbmax_time = datetime.datetime.fromtimestamp(int(time0))
    dayblock = dbmax - 144
    weekblock = dbmax - 144*7
    res = cur.execute('SELECT time,difficulty FROM block WHERE height=?', (dayblock,))
    time1, diff1 = res.fetchone()
    delta = dbmax_time - datetime.datetime.fromtimestamp(int(time1))
    minperblock = '%.2f' % (delta.total_seconds() / 144.0 / 60)
    res = cur.execute('SELECT difficulty FROM block WHERE height=?', (weekblock,))
    diff7 = res.fetchone()[0]
    retarget = params['DifficultyAdjustmentInterval']
    blocktime = params['PowTargetSpacing']
    progress = dbmax % retarget
    nextdiff = diff0
    if progress > 0:
        res = cur.execute('SELECT time FROM block WHERE height=?', (dbmax-progress,))
        time = res.fetchone()[0]
        delta = dbmax_time - datetime.datetime.fromtimestamp(int(time))
        estintervaltime = delta.total_seconds() + blocktime * (retarget - progress)
        nextdiff = float(diff0) * (blocktime*retarget) / float(estintervaltime)
    stats = {'minperblock': minperblock, 'diff0':diff0, 'diff1':diff1, 'diff7':diff7,
             'progress': '%d of %d' % (progress, retarget), 'nextdiff': nextdiff}
    return render_template('stats-page.html', chaininfo=chaininfo, topinfo=topinfo,
                           topminers=topminers, stats=stats)

@app.route("/search/")
def search():
    err = 'Unsupported search string.'
    s = request.args.get('search','').strip()
    if len(s) < 10:
        # assume integer block number
        try:
            startblock = int(s)
            if startblock < 0:
                startblock = 0
            return redirect(url_for('main_page', startblock=startblock))
        except ValueError:
            err = 'Cannot parse block number.'
    
    con = sqlite3.connect(DBFILE)
    cur = con.cursor()
    
    if len(s) == 64:
        # assume hex block hash, merkle hash, or tx hash
        # start with tx and maybe get blockhash
        res = cur.execute('SELECT blockhash FROM tx WHERE txid=?', (s,))
        try:
            s = res.fetchone()[0]
        except TypeError:
            pass
        res = cur.execute('SELECT height FROM block WHERE hash=? OR merkleroot=?', (s,s))
        try:
            blocknr = res.fetchone()[0]
            return redirect(url_for('block_page', blocknr=blocknr))
        except TypeError:
            err = 'Cannot find block, merkle, or transaction hash.'

    # Otherwise, check if address
    res = cur.execute('SELECT COUNT(*) FROM output WHERE address=?', (s,))
    if int(res.fetchone()[0]) > 0:
        return redirect(url_for('address_page', address=s))
    
    topinfo = latest_topinfo(cur)
    return render_template('searchfail-page.html', chaininfo=chaininfo, topinfo=topinfo, search=s, err=err)

