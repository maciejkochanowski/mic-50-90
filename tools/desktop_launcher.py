"""Entry point for the portable Windows application."""
import multiprocessing

if __name__ == '__main__':
    multiprocessing.freeze_support()
    from mic_50_90.gui import main
    raise SystemExit(main())
