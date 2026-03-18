"use client";

import { useMemo, useState } from "react";

type DatabaseName = "ecommerce" | "saas";

type QuestionCategory = {
  title: string;
  questions: string[];
};

type SampleQuestionsProps = {
  database: DatabaseName;
  onQuestionSelect: (question: string) => void;
};

const BASE_CATEGORIES: QuestionCategory[] = [
  {
    title: "Revenue & Sales",
    questions: [
      "What is our total revenue by quarter for 2024?",
      "Which product categories are growing fastest?",
      "Show me our top 10 customers by lifetime value",
    ],
  },
  {
    title: "Customer Analytics",
    questions: [
      "What is our customer retention rate by cohort?",
      "Which cities generate the most revenue?",
      "How does average order value differ by customer segment?",
    ],
  },
  {
    title: "Operational",
    questions: [
      "What is our return rate by product category?",
      "What is the average shipping time by ship mode?",
      "Show orders with discounts over 20% and their profit margins",
    ],
  },
];

const SAAS_CATEGORY: QuestionCategory = {
  title: "SaaS Metrics",
  questions: [
    "What is our MRR growth over the last 12 months?",
    "What is our churn rate by plan type?",
    "Which features are most used by enterprise customers?",
  ],
};

const INITIAL_VISIBLE = 5;

export default function SampleQuestions({ database, onQuestionSelect }: SampleQuestionsProps) {
  const [visibleCount, setVisibleCount] = useState<number>(INITIAL_VISIBLE);

  const categories = useMemo<QuestionCategory[]>(() => {
    if (database === "saas") {
      return [...BASE_CATEGORIES, SAAS_CATEGORY];
    }
    return BASE_CATEGORIES;
  }, [database]);

  const allQuestions = useMemo(() => categories.flatMap((c) => c.questions), [categories]);

  const visibleSet = useMemo(() => {
    const shown = allQuestions.slice(0, visibleCount);
    return new Set(shown);
  }, [allQuestions, visibleCount]);

  const hasMore = visibleCount < allQuestions.length;

  return (
    <div>
      <p className="mb-2 text-xs uppercase tracking-wide text-slate-400">Sample Questions</p>
      <div className="space-y-3">
        {categories.map((category) => {
          const visibleQuestions = category.questions.filter((q) => visibleSet.has(q));
          if (!visibleQuestions.length) {
            return null;
          }

          return (
            <section key={category.title} className="space-y-2">
              <h3 className="text-[11px] font-medium uppercase tracking-wider text-slate-500">{category.title}</h3>
              <div className="flex flex-wrap gap-2">
                {visibleQuestions.map((question) => (
                  <button
                    key={question}
                    type="button"
                    onClick={() => onQuestionSelect(question)}
                    className="rounded-full border border-slate-700 bg-slate-900/70 px-3 py-1.5 text-left text-xs text-slate-200 transition hover:border-blue-500 hover:text-white"
                  >
                    {question}
                  </button>
                ))}
              </div>
            </section>
          );
        })}

        {hasMore ? (
          <button
            type="button"
            onClick={() => setVisibleCount((prev) => Math.min(prev + 4, allQuestions.length))}
            className="rounded border border-slate-700 px-3 py-1 text-xs text-slate-300 hover:border-blue-600 hover:text-slate-100"
          >
            Show more
          </button>
        ) : null}
      </div>
    </div>
  );
}
