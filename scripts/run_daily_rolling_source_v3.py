"""Uninstalled rolling daily source CLI; no user-controlled clock."""
import argparse,json
from pathlib import Path
from data.strategy_daily_rolling_runner_v3 import run_rolling_sources
from data.strategy_daily_rolling_parent_v3 import bounded_read

def main():
 parser=argparse.ArgumentParser()
 parser.add_argument('--root',required=True);parser.add_argument('--config-path',required=True)
 parser.add_argument('--config-sha256',required=True);parser.add_argument('--execute',action='store_true')
 args=parser.parse_args()
 print(json.dumps(run_rolling_sources(root=args.root,configuration_bytes=bounded_read(Path(args.config_path)),configuration_sha256=args.config_sha256,execute=args.execute),ensure_ascii=False))
if __name__=='__main__':main()
