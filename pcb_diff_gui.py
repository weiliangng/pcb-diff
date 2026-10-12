from pcb_diff.gui import main
if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description='PCB Diff desktop application')
    parser.add_argument('--self-test', metavar='OUTPUT_DIRECTORY', help='Run a hidden interface comparison and write its results')
    args = parser.parse_args()
    main(self_test_dir=args.self_test)
