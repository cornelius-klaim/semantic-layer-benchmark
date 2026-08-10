---
type: dataset
title: Cross-Domain Enterprise (Learning x Sales x HR)
resource: d2
tags: [retail, sales]
---
# Cross-Domain Enterprise (Learning x Sales x HR)
Three source systems that share no obvious key. Sales opportunities are keyed by employee_id; the LMS (learners, completions, assessments) is keyed by a messy email; the HR bridge is the ONLY path between them, and only after email normalization (lowercase, strip the legacy '.contractor' alias). The certified rep_course_flags rollup resolves that identity join once.

## Grain
opportunities is one row per rep (quarter). assessment_scores is one row per (learner, course). A learner maps to exactly one employee via the normalized email bridge. Grouping attainment by a course flag requires the certified per-rep rollup.

## Concept documents
- Tables: [assessment_scores](./table_assessment_scores.md), [courses](./table_courses.md), [hr_bridge](./table_hr_bridge.md), [opportunities](./table_opportunities.md), [rep_course_flags](./table_rep_course_flags.md)
- Metrics: [avg_quota_attainment](./metric_avg_quota_attainment.md), [total_revenue](./metric_total_revenue.md), [rep_count](./metric_rep_count.md), [avg_assessment_score](./metric_avg_assessment_score.md)

## Joins
- `opportunities` relates to `hr_bridge` as **many-to-one**, joined on `opportunities.employee_id = hr_bridge.employee_id`. Because it is many-to-one, aggregating a `hr_bridge`-grain measure across joined `opportunities` rows will double-count (fan-out).
- `opportunities` relates to `rep_course_flags` as **many-to-one**, joined on `opportunities.employee_id = rep_course_flags.employee_id`. Because it is many-to-one, aggregating a `rep_course_flags`-grain measure across joined `opportunities` rows will double-count (fan-out).
- `assessment_scores` relates to `learners` as **many-to-one**, joined on `assessment_scores.learner_id = learners.learner_id`. Because it is many-to-one, aggregating a `learners`-grain measure across joined `assessment_scores` rows will double-count (fan-out).
- `assessment_scores` relates to `courses` as **many-to-one**, joined on `assessment_scores.course_id = courses.course_id`. Because it is many-to-one, aggregating a `courses`-grain measure across joined `assessment_scores` rows will double-count (fan-out).
- `learners` relates to `hr_bridge` as **many-to-one**, joined on `lower(replace(learners.email,'.contractor','')) = lower(hr_bridge.work_email)`. Because it is many-to-one, aggregating a `hr_bridge`-grain measure across joined `learners` rows will double-count (fan-out).

## Vocabulary
