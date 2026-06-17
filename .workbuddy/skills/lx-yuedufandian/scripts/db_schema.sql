CREATE SCHEMA IF NOT EXISTS lxfandian;

CREATE TABLE IF NOT EXISTS lxfandian.imports (
    id text PRIMARY KEY,
    month text NOT NULL,
    import_type text NOT NULL DEFAULT 'full',
    work_dir text NOT NULL,
    rules_hash text NOT NULL,
    rules_text text NOT NULL,
    status text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    confirmed_at timestamptz
);

CREATE TABLE IF NOT EXISTS lxfandian.src_sheets (
    id bigserial PRIMARY KEY,
    import_id text NOT NULL REFERENCES lxfandian.imports(id) ON DELETE CASCADE,
    file_role text NOT NULL,
    file_path text NOT NULL,
    file_hash text NOT NULL,
    sheet_name text NOT NULL,
    row_count integer NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS lxfandian.bill_raw (
    id bigserial PRIMARY KEY,
    import_id text NOT NULL REFERENCES lxfandian.imports(id) ON DELETE CASCADE,
    src_sheet_id bigint NOT NULL REFERENCES lxfandian.src_sheets(id) ON DELETE CASCADE,
    row_no integer NOT NULL,
    partition_date date,
    brand_name text,
    city_name text,
    tr_type text,
    channel text,
    gross_receivable numeric NOT NULL DEFAULT 0,
    spring_service_fee numeric NOT NULL DEFAULT 0,
    raw_payload jsonb NOT NULL
);

CREATE TABLE IF NOT EXISTS lxfandian.bill_agg (
    id bigserial PRIMARY KEY,
    import_id text NOT NULL REFERENCES lxfandian.imports(id) ON DELETE CASCADE,
    src_sheet_id bigint NOT NULL REFERENCES lxfandian.src_sheets(id) ON DELETE CASCADE,
    partition_date date,
    brand_name text NOT NULL,
    city_name text NOT NULL,
    tr_type text NOT NULL,
    channel text NOT NULL,
    gross_receivable numeric NOT NULL,
    spring_service_fee numeric NOT NULL,
    row_count integer NOT NULL
);

ALTER TABLE lxfandian.bill_agg
    ADD COLUMN IF NOT EXISTS partition_date date;

CREATE TABLE IF NOT EXISTS lxfandian.proc_raw (
    id bigserial PRIMARY KEY,
    import_id text NOT NULL REFERENCES lxfandian.imports(id) ON DELETE CASCADE,
    src_sheet_id bigint NOT NULL REFERENCES lxfandian.src_sheets(id) ON DELETE CASCADE,
    brand_name text,
    city_name text,
    operator_name text,
    metric_date text,
    raw_payload jsonb NOT NULL
);

CREATE TABLE IF NOT EXISTS lxfandian.targets (
    id bigserial PRIMARY KEY,
    import_id text NOT NULL REFERENCES lxfandian.imports(id) ON DELETE CASCADE,
    src_sheet_id bigint NOT NULL REFERENCES lxfandian.src_sheets(id) ON DELETE CASCADE,
    target_type text NOT NULL,
    operator_entity text,
    brand_name text,
    cities_text text,
    target_payload jsonb NOT NULL
);

CREATE TABLE IF NOT EXISTS lxfandian.open_city (
    id bigserial PRIMARY KEY,
    import_id text NOT NULL REFERENCES lxfandian.imports(id) ON DELETE CASCADE,
    src_sheet_id bigint NOT NULL REFERENCES lxfandian.src_sheets(id) ON DELETE CASCADE,
    brand_name text,
    city_name text,
    settlement_type text,
    settlement_unit text,
    settlement_item text,
    open_date text,
    incentive_period text,
    rate numeric NOT NULL DEFAULT 0,
    settlement_period text,
    rebate_basis numeric NOT NULL DEFAULT 0,
    reward_amount numeric NOT NULL DEFAULT 0,
    remark1 text,
    remark2 text,
    raw_payload jsonb NOT NULL
);

CREATE TABLE IF NOT EXISTS lxfandian.runs (
    id text PRIMARY KEY,
    import_id text REFERENCES lxfandian.imports(id) ON DELETE SET NULL,
    data_source text NOT NULL DEFAULT 'db',
    month text NOT NULL,
    contacts jsonb NOT NULL,
    exclude_operators jsonb NOT NULL,
    rules_hash text NOT NULL,
    rules_text text NOT NULL,
    status text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    confirmed_at timestamptz
);

CREATE TABLE IF NOT EXISTS lxfandian.scope (
    id bigserial PRIMARY KEY,
    run_id text NOT NULL REFERENCES lxfandian.runs(id) ON DELETE CASCADE,
    operator_entity text NOT NULL,
    brand_name text NOT NULL,
    city_name text NOT NULL,
    contact_person text NOT NULL
);

CREATE TABLE IF NOT EXISTS lxfandian.base_agg (
    id bigserial PRIMARY KEY,
    run_id text NOT NULL REFERENCES lxfandian.runs(id) ON DELETE CASCADE,
    brand_name text NOT NULL,
    city_name text NOT NULL,
    gross_all numeric NOT NULL,
    gross_receivable numeric NOT NULL,
    spring_service_fee numeric NOT NULL,
    rebate_base_before_open_city numeric NOT NULL DEFAULT 0,
    open_city_excluded_base numeric NOT NULL DEFAULT 0,
    rebate_base numeric NOT NULL,
    filtered_row_count integer NOT NULL
);

ALTER TABLE lxfandian.base_agg
    ADD COLUMN IF NOT EXISTS rebate_base_before_open_city numeric NOT NULL DEFAULT 0;

ALTER TABLE lxfandian.base_agg
    ADD COLUMN IF NOT EXISTS open_city_excluded_base numeric NOT NULL DEFAULT 0;

CREATE TABLE IF NOT EXISTS lxfandian.results (
    id bigserial PRIMARY KEY,
    run_id text NOT NULL REFERENCES lxfandian.runs(id) ON DELETE CASCADE,
    month text NOT NULL,
    operator_entity text NOT NULL,
    brand_name text NOT NULL,
    contact_person text NOT NULL,
    gross_all numeric NOT NULL DEFAULT 0,
    rebate_base_before_open_city numeric NOT NULL DEFAULT 0,
    open_city_excluded_base numeric NOT NULL DEFAULT 0,
    rebate_base numeric NOT NULL,
    completed_orders numeric NOT NULL,
    completed_orders_for_target numeric NOT NULL DEFAULT 0,
    scale_rate numeric NOT NULL,
    process_rate numeric NOT NULL,
    process_completion_rate numeric NOT NULL DEFAULT 0,
    monthly_order_rate numeric NOT NULL,
    extra_rate numeric NOT NULL,
    final_rate numeric NOT NULL,
    point_rebate_amount numeric NOT NULL,
    new_city_amount numeric NOT NULL DEFAULT 0,
    new_city_rate numeric NOT NULL DEFAULT 0,
    total_rebate_amount numeric NOT NULL,
    total_rate numeric NOT NULL,
    tier_name text,
    status text NOT NULL,
    reason text
);

ALTER TABLE lxfandian.results
    ADD COLUMN IF NOT EXISTS rebate_base_before_open_city numeric NOT NULL DEFAULT 0;

ALTER TABLE lxfandian.results
    ADD COLUMN IF NOT EXISTS open_city_excluded_base numeric NOT NULL DEFAULT 0;

ALTER TABLE lxfandian.results
    ADD COLUMN IF NOT EXISTS process_completion_rate numeric NOT NULL DEFAULT 0;

CREATE TABLE IF NOT EXISTS lxfandian.proc_detail (
    id bigserial PRIMARY KEY,
    run_id text NOT NULL REFERENCES lxfandian.runs(id) ON DELETE CASCADE,
    operator_entity text NOT NULL,
    brand_name text NOT NULL,
    metric_key text NOT NULL,
    metric_name text NOT NULL,
    metric_value text,
    threshold_text text,
    passed boolean NOT NULL,
    base_rate numeric NOT NULL,
    coefficient numeric NOT NULL,
    final_rate numeric NOT NULL,
    source_sheet text,
    reason text
);

CREATE INDEX IF NOT EXISTS idx_lxfandian_imports_month
    ON lxfandian.imports(month, import_type, confirmed_at DESC);

CREATE INDEX IF NOT EXISTS idx_lxfandian_src_sheets_import
    ON lxfandian.src_sheets(import_id, file_role, sheet_name);

CREATE INDEX IF NOT EXISTS idx_lxfandian_bill_raw_brand_city_date
    ON lxfandian.bill_raw(import_id, brand_name, city_name, partition_date);

CREATE INDEX IF NOT EXISTS idx_lxfandian_bill_raw_filter
    ON lxfandian.bill_raw(import_id, tr_type, channel);

CREATE INDEX IF NOT EXISTS idx_lxfandian_bill_agg_brand_city
    ON lxfandian.bill_agg(import_id, brand_name, city_name);

CREATE INDEX IF NOT EXISTS idx_lxfandian_bill_agg_brand_city_date
    ON lxfandian.bill_agg(import_id, brand_name, city_name, partition_date);

CREATE INDEX IF NOT EXISTS idx_lxfandian_bill_agg_filter
    ON lxfandian.bill_agg(import_id, tr_type, channel);

CREATE INDEX IF NOT EXISTS idx_lxfandian_proc_raw_import
    ON lxfandian.proc_raw(import_id, src_sheet_id);

CREATE INDEX IF NOT EXISTS idx_lxfandian_open_city_import
    ON lxfandian.open_city(import_id, brand_name, city_name);

CREATE INDEX IF NOT EXISTS idx_lxfandian_results_run
    ON lxfandian.results(run_id);

CREATE INDEX IF NOT EXISTS idx_lxfandian_results_month_operator
    ON lxfandian.results(month, operator_entity, brand_name);

CREATE INDEX IF NOT EXISTS idx_lxfandian_proc_detail_run
    ON lxfandian.proc_detail(run_id);
