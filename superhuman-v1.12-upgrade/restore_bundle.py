"""Standalone v1.12 restore helper. Empty target required; dependencies not needed."""
import argparse
from pathlib import Path
import types
from patches import build


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--bundle',required=True);parser.add_argument('--target',required=True)
    args=parser.parse_args();source=Path(__file__).resolve().parent
    try:
        reference=source/'reference'
        code=build('hosted/transfer.py',(reference/'hosted/transfer.py').read_text(encoding='utf-8'),reference)
        module=types.ModuleType('superhuman_transfer_v112')
        exec(compile(code,'superhuman_transfer_v112','exec'),module.__dict__)
        print(module.restore(args.bundle,args.target))
    except (ValueError,OSError) as exc:parser.exit(1,str(exc)+'\n')


if __name__=='__main__':main()
