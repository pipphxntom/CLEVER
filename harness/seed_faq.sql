INSERT INTO faq_entries (question, answer, source) VALUES
('what is the collections SLA', 'Standard collections SLA is 30 days from invoice due date. Escalation at 60 days.', 'manual'),
('who handles disputes', 'Disputes are handled by the AR team. Submit via the dispute intent with supporting docs.', 'manual')
ON CONFLICT (question) DO NOTHING;
