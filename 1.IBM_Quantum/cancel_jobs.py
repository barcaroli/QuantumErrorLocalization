"""
Cancel all currently queued or running IBM Quantum Runtime jobs on the
saved account. Useful after stopping a local script with Ctrl+C: jobs
already submitted keep running on IBM's side even after the local
process is killed, so they must be cancelled separately.

Usage:
    python cancel_jobs.py
"""

from qiskit_ibm_runtime import QiskitRuntimeService


def main():
    service = QiskitRuntimeService()
    jobs = service.jobs(pending=True, limit=200)  # QUEUED or RUNNING only

    if not jobs:
        print("No queued or running jobs found.")
        return

    print(f"Found {len(jobs)} queued/running job(s):")
    for job in jobs:
        print(f"  {job.job_id()}  status={job.status()}  backend={job.backend()}")

    confirm = input("\nCancel ALL of these jobs? [y/N]: ").strip().lower()
    if confirm != "y":
        print("Aborted, no jobs cancelled.")
        return

    for job in jobs:
        try:
            job.cancel()
            print(f"  Cancelled {job.job_id()}")
        except Exception as e:
            print(f"  Could not cancel {job.job_id()}: {e}")


if __name__ == "__main__":
    main()
