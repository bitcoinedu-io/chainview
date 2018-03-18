# Common config for chainview

VERSION = '1.0'
GITHUB = 'https://github.com/bitcoinedu-io/chainview'

DBFILE = 'chainview-db.sqlite3'

rpc_user = 'user'
rpc_pass = 'pass'
URL = 'http://%s:%s@localhost:8332' % (rpc_user, rpc_pass)

chaininfo = {
    'name': 'Bitcoin Edu',
    'unit': 'BTE'
    }

params = {
    'SubsidyHalvingInterval': 210000,     # blocks, miner reward halving
    'PowTargetTimespan': 1*24*60*60,      # sec, retarget time: one day
    'PowTargetSpacing': 10*60,            # sec, block time 10 min
    'DifficultyAdjustmentInterval': 144   # blocks, PowTargetTimespan / PowTargetSpacing
    }
