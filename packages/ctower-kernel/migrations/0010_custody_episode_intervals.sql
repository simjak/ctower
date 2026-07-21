ALTER TABLE assignment_intervals
    ADD COLUMN episode_number integer NOT NULL DEFAULT 1 CHECK (episode_number >= 1),
    ADD CONSTRAINT assignment_intervals_episode_fk
        FOREIGN KEY (ticket_id, episode_number)
        REFERENCES lifecycle_episodes(ticket_id, episode_number);

ALTER TABLE assignment_intervals ALTER COLUMN episode_number DROP DEFAULT;
