-- ============================================================
-- database/schema.sql
--
-- InsightAI database schema (MySQL 8.0+).
--
-- This mirrors the SQLAlchemy models defined in backend/models.py.
-- In normal development, backend/main.py's startup lifespan already
-- creates these tables automatically via Base.metadata.create_all().
-- This file exists for:
--   1. Docker's auto-init (mounted via docker-compose.yml into
--      /docker-entrypoint-initdb.d/)
--   2. Manual setup without Docker
--   3. Plain-SQL documentation of the schema
-- ============================================================

CREATE DATABASE IF NOT EXISTS insightai
    CHARACTER SET utf8mb4
    COLLATE utf8mb4_unicode_ci;

USE insightai;

-- ------------------------------------------------------------
-- Table: users
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS users (
    id                INT AUTO_INCREMENT PRIMARY KEY,
    public_id         VARCHAR(36) NOT NULL,
    full_name         VARCHAR(150) NOT NULL,
    email             VARCHAR(255) NOT NULL,
    hashed_password   VARCHAR(255) NOT NULL,
    role              ENUM('admin', 'user') NOT NULL DEFAULT 'user',
    is_active         BOOLEAN NOT NULL DEFAULT TRUE,
    created_at        DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at        DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,

    UNIQUE KEY uq_users_public_id (public_id),
    UNIQUE KEY uq_users_email (email),
    KEY ix_users_public_id (public_id),
    KEY ix_users_email (email)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ------------------------------------------------------------
-- Table: datasets
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS datasets (
    id                  INT AUTO_INCREMENT PRIMARY KEY,
    public_id           VARCHAR(36) NOT NULL,
    owner_id            INT NOT NULL,
    original_filename   VARCHAR(255) NOT NULL,
    stored_filename      VARCHAR(255) NOT NULL,
    file_size_bytes     BIGINT NOT NULL,
    row_count           INT NULL,
    column_count        INT NULL,
    status              ENUM('uploaded', 'cleaning', 'ready', 'failed') NOT NULL DEFAULT 'uploaded',
    error_message       TEXT NULL,
    uploaded_at         DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,

    UNIQUE KEY uq_datasets_public_id (public_id),
    KEY ix_datasets_public_id (public_id),
    KEY ix_datasets_owner_id (owner_id),

    CONSTRAINT fk_datasets_owner
        FOREIGN KEY (owner_id) REFERENCES users(id)
        ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ------------------------------------------------------------
-- Table: reports
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS reports (
    id            INT AUTO_INCREMENT PRIMARY KEY,
    public_id     VARCHAR(36) NOT NULL,
    dataset_id    INT NOT NULL,
    title         VARCHAR(255) NOT NULL,
    format        ENUM('pdf', 'excel', 'csv') NOT NULL,
    file_path     VARCHAR(500) NOT NULL,
    created_at    DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,

    UNIQUE KEY uq_reports_public_id (public_id),
    KEY ix_reports_public_id (public_id),
    KEY ix_reports_dataset_id (dataset_id),

    CONSTRAINT fk_reports_dataset
        FOREIGN KEY (dataset_id) REFERENCES datasets(id)
        ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ------------------------------------------------------------
-- Table: chat_history
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS chat_history (
    id            INT AUTO_INCREMENT PRIMARY KEY,
    dataset_id    INT NOT NULL,
    role          VARCHAR(20) NOT NULL,
    message       TEXT NOT NULL,
    created_at    DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,

    KEY ix_chat_history_dataset_id (dataset_id),

    CONSTRAINT fk_chat_history_dataset
        FOREIGN KEY (dataset_id) REFERENCES datasets(id)
        ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ------------------------------------------------------------
-- Table: query_history
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS query_history (
    id                        INT AUTO_INCREMENT PRIMARY KEY,
    dataset_id                INT NOT NULL,
    natural_language_query    TEXT NOT NULL,
    generated_sql             TEXT NOT NULL,
    was_successful             BOOLEAN NOT NULL DEFAULT TRUE,
    created_at                DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,

    KEY ix_query_history_dataset_id (dataset_id),

    CONSTRAINT fk_query_history_dataset
        FOREIGN KEY (dataset_id) REFERENCES datasets(id)
        ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;