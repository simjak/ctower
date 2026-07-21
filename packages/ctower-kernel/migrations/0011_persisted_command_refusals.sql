ALTER TABLE command_results DROP CONSTRAINT command_results_status_code_check;
ALTER TABLE command_results ADD CONSTRAINT command_results_status_code_check CHECK (
    status_code BETWEEN 200 AND 299 OR status_code BETWEEN 400 AND 499
);
