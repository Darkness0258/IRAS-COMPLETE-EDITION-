from __future__ import annotations
import time
from rich.console import Console
from iras.bootstrap import build_runtime
from iras.models import PermissionLevel

def main():
    c=Console(); rt=build_runtime(approval_callback=None,hard_cap=PermissionLevel.SAFE_ACTION); c.print('IRAS scheduler running. Scheduled jobs may only use READ/SAFE_ACTION tools without interactive approval.')
    try:
        while True:
            for row in rt.automations.due():
                try: result=rt.agent.handle(row['prompt'])
                except Exception as e: result=f'ERROR: {e}'
                rt.automations.finish(row,result); c.print(f"Job {row['id']}: {result}")
            time.sleep(5)
    except KeyboardInterrupt: pass
