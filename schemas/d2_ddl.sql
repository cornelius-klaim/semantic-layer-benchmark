CREATE TABLE hr_bridge (
  employee_id BIGINT,
  work_email VARCHAR,
  region VARCHAR,
  tenure_years BIGINT
);

CREATE TABLE sales_reps (
  employee_id BIGINT,
  rep_name VARCHAR,
  sales_region VARCHAR
);

CREATE TABLE opportunities (
  opp_id BIGINT,
  employee_id BIGINT,
  quarter VARCHAR,
  closed_revenue DOUBLE,
  quota_attainment DOUBLE
);

CREATE TABLE learners (
  learner_id BIGINT,
  email VARCHAR
);

CREATE TABLE courses (
  course_id BIGINT,
  course_name VARCHAR
);

CREATE TABLE course_completions (
  learner_id BIGINT,
  course_id BIGINT
);

CREATE TABLE assessment_scores (
  learner_id BIGINT,
  course_id BIGINT,
  score DOUBLE
);
