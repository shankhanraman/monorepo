import { describe, expect, it } from 'vitest';
import { formatTime } from './time';

describe('formatTime', () => {
  it('formats under an hour as m:ss', () => {
    expect(formatTime(0)).toBe('0:00');
    expect(formatTime(5)).toBe('0:05');
    expect(formatTime(65)).toBe('1:05');
    expect(formatTime(720)).toBe('12:00');
    expect(formatTime(3599)).toBe('59:59');
  });
  it('formats an hour and up as h:mm:ss', () => {
    expect(formatTime(3600)).toBe('1:00:00');
    expect(formatTime(3605)).toBe('1:00:05');
    expect(formatTime(3725)).toBe('1:02:05');
    expect(formatTime(36000)).toBe('10:00:00');
  });
  it('floors fractions and clamps bad input to 0', () => {
    expect(formatTime(61.9)).toBe('1:01');
    expect(formatTime(-3)).toBe('0:00');
    expect(formatTime(Number.NaN)).toBe('0:00');
  });
});
