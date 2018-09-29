python3 -m cProfile -o stats.prof chainview_fill.py

# Then:
#
# python3 -m pstats stats.prof
# sort cumtime
# stats 20
