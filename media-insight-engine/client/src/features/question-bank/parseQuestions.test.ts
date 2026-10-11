import { describe, expect, it } from 'vitest';
import { parseCsv, parseQuestions } from './parseQuestions';

describe('parseQuestions (text)', () => {
  it('takes one question per line, trimmed', () => {
    expect(parseQuestions('  What is EA?  \nIs the SAT required?\r\nHow long is the essay?')).toEqual({
      questions: ['What is EA?', 'Is the SAT required?', 'How long is the essay?'],
      error: null,
    });
  });

  it('drops empty lines and exact duplicates, keeping the first', () => {
    const r = parseQuestions('\nWhat is EA?\n\n   \nWhat is EA?\nwhat is EA?\n What is EA? \n');
    expect(r.questions).toEqual(['What is EA?', 'what is EA?']);
    expect(r.error).toBeNull();
  });

  it('does not treat a "question" first line as a header in plain text', () => {
    expect(parseQuestions('question\nIs the SAT required?').questions).toEqual(['question', 'Is the SAT required?']);
  });

  it('rejects an empty list', () => {
    expect(parseQuestions('\n  \n').error).toMatch(/at least one question/);
    expect(parseQuestions('').error).not.toBeNull();
  });

  it('accepts 100 questions and rejects 101', () => {
    const lines = (n: number) => Array.from({ length: n }, (_, i) => `Question number ${i + 1}?`).join('\n');
    expect(parseQuestions(lines(100)).error).toBeNull();
    const r = parseQuestions(lines(101));
    expect(r.questions).toHaveLength(101);
    expect(r.error).toMatch(/Too many questions: 101/);
  });

  it('enforces 3–2000 characters per question', () => {
    expect(parseQuestions('abc').error).toBeNull();
    expect(parseQuestions('Fine question?\nab').error).toMatch(/question 2 \("ab"\) is shorter than 3/);
    expect(parseQuestions('x'.repeat(2000)).error).toBeNull();
    expect(parseQuestions('x'.repeat(2001)).error).toMatch(/2001 characters; the limit is 2000/);
  });

  it('summarises many length problems', () => {
    const r = parseQuestions('a\nb\nc\nd\ne');
    expect(r.error).toMatch(/and 2 more/);
  });
});

describe('parseQuestions (csv)', () => {
  it('uses the first column and drops a "question" header in any case', () => {
    const csv = 'Question,notes\nWhat is EA?,early\nIs the SAT required?,testing\n';
    expect(parseQuestions(csv, 'csv')).toEqual({
      questions: ['What is EA?', 'Is the SAT required?'],
      error: null,
    });
    expect(parseQuestions('QUESTION\nWhat is EA?', 'csv').questions).toEqual(['What is EA?']);
    expect(parseQuestions(' question \nWhat is EA?', 'csv').questions).toEqual(['What is EA?']);
  });

  it('keeps the first row when it is not a header', () => {
    expect(parseQuestions('What is EA?\nIs the SAT required?', 'csv').questions).toEqual([
      'What is EA?',
      'Is the SAT required?',
    ]);
  });

  it('handles quoted fields with commas, escaped quotes and newlines', () => {
    const csv =
      'question,tag\r\n' +
      '"How do Yale, MIT and Harvard differ?",compare\r\n' +
      '"What does ""demonstrated interest"" mean?",misc\r\n' +
      '"A question\nover two lines?",x\r\n';
    expect(parseQuestions(csv, 'csv').questions).toEqual([
      'How do Yale, MIT and Harvard differ?',
      'What does "demonstrated interest" mean?',
      'A question\nover two lines?',
    ]);
  });

  it('drops empty rows and duplicates, and strips a BOM', () => {
    const csv = '﻿question\n\nWhat is EA?\n,empty first column\n"What is EA?",dup\n';
    expect(parseQuestions(csv, 'csv')).toEqual({ questions: ['What is EA?'], error: null });
  });

  it('applies the length limits to CSV too', () => {
    expect(parseQuestions('question\nok', 'csv').error).toMatch(/shorter than 3/);
    expect(parseQuestions('question\n', 'csv').error).toMatch(/at least one question/);
  });
});

describe('parseCsv', () => {
  it('splits rows and fields', () => {
    expect(parseCsv('a,b\n"c,d",e\n"f ""g""",')).toEqual([
      ['a', 'b'],
      ['c,d', 'e'],
      ['f "g"', ''],
    ]);
  });
});
