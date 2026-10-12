ALTER TABLE users
    ADD COLUMN IF NOT EXISTS username VARCHAR(30);

DO $$
BEGIN
    IF EXISTS (
        SELECT 1
        FROM information_schema.columns
        WHERE table_name = 'users'
          AND column_name = 'hashed_password'
    )
    AND NOT EXISTS (
        SELECT 1
        FROM information_schema.columns
        WHERE table_name = 'users'
          AND column_name = 'password_hash'
    )
    THEN
        ALTER TABLE users
            RENAME COLUMN hashed_password TO password_hash;
    END IF;
END
$$;