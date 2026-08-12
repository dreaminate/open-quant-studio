UPDATE jobs
SET status = 'failed',
    error_code = 'worker_interrupted_by_upgrade',
    error_message = 'Formal Run interrupted by M4 worker upgrade',
    finished_at = strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
WHERE job_type = 'formal.run' AND status = 'running';

CREATE UNIQUE INDEX jobs_single_running_formal_idx
ON jobs((1))
WHERE job_type = 'formal.run' AND status = 'running';
