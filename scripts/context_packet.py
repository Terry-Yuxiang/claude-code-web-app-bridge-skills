#!/usr/bin/env python3
import argparse
import json
from pathlib import Path


def main():
    p = argparse.ArgumentParser(description='Build a compact Claude Code context packet')
    p.add_argument('--os')
    p.add_argument('--repo')
    p.add_argument('--app')
    p.add_argument('--node')
    p.add_argument('--package-manager')
    p.add_argument('--browser-context')
    p.add_argument('--command')
    p.add_argument('--error')
    p.add_argument('--goal')
    p.add_argument('--constraints')
    args = p.parse_args()

    packet = {
        'os': args.os or '',
        'repo': args.repo or '',
        'app': args.app or '',
        'node': args.node or '',
        'packageManager': args.package_manager or '',
        'browserContext': args.browser_context or '',
        'command': args.command or '',
        'error': args.error or '',
        'goal': args.goal or '',
        'constraints': args.constraints or '',
    }
    print(json.dumps(packet, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
