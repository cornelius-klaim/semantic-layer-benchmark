---
type: metric
title: avg_assessment_score
resource: d2.metric.avg_assessment_score
tags: [certified]
---
# Metric: avg_assessment_score

Average LMS assessment score (0-100). Joins to reps only through the certified email-normalization bridge.

**Definition.** `AVG(assessment_scores.score)`

**Grain.** This measure is additive at the `assessment_scores` grain. Breaking it down by a dimension finer than that grain double-counts.

**Also called:** assessment score, test score, average score.
