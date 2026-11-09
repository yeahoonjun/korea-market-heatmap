"""Run qa/heatmap/verify.py unchanged, but with the live build on this worktree's dev Worker (port 8798).
usage: run_verify.py [snapshot|live]"""
import sys, runpy
sys.path.insert(0, '/home/claude/hm-heatmap/qa/heatmap')
import common
common.LIVE_URL = 'http://127.0.0.1:8798/'
common.BUILDS['live'] = common.LIVE_URL
runpy.run_path('/home/claude/hm-heatmap/qa/heatmap/verify.py', run_name='__main__')
