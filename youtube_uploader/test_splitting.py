
import unittest
from typing import List, Optional

# Mocking the classes from main.py for testing purposes
class VideoBatch:
    def __init__(self, channel: str, date: str, files: List[str], part_number: int = 1, total_parts: int = 1):
        self.channel = channel
        self.date = date
        self.files = sorted(files)
        self.part_number = part_number
        self.total_parts = total_parts
        
    def __repr__(self):
        return f"Batch(part={self.part_number}/{self.total_parts}, files={len(self.files)})"

class MockUploaderService:
    MAX_DURATION_SECONDS = 41400 # 11.5 hours

    def _get_video_duration(self, filepath: str) -> float:
        # Mock: All files are exactly 1 hour (3600s)
        return 3600.0

    def _find_batches(self, file_list: List[str]) -> List[VideoBatch]:
        """Same logic as implemented in main.py, but using input list"""
        # Assume all files belong to same channel/date for this test
        files = sorted(file_list)
        
        final_batches = []
        
        # Check total duration and split if necessary
        current_batch_files = []
        current_duration = 0.0
        split_batches = []
        
        for file_path in files:
            duration = self._get_video_duration(file_path)
            
            if current_duration + duration > self.MAX_DURATION_SECONDS and current_batch_files:
                split_batches.append(current_batch_files)
                current_batch_files = []
                current_duration = 0.0
            
            current_batch_files.append(file_path)
            current_duration += duration
        
        if current_batch_files:
            split_batches.append(current_batch_files)
        
        total_parts = len(split_batches)
        for i, batch_files in enumerate(split_batches):
            part_number = i + 1
            if total_parts > 1:
                    batch_obj = VideoBatch("TestCh", "2024-01-01", batch_files, part_number, total_parts)
            else:
                    batch_obj = VideoBatch("TestCh", "2024-01-01", batch_files)
            
            final_batches.append(batch_obj)
            
        return final_batches

class TestSplitting(unittest.TestCase):
    def test_splitting_24_hours(self):
        service = MockUploaderService()
        # Create 24 files, each 1 hour long
        files = [f"video_{i:02d}.mp4" for i in range(24)]
        
        batches = service._find_batches(files)
        
        print(f"\nCreated {len(batches)} batches:")
        for b in batches:
            print(b)

        # Expected:
        # 11.5h limit. Each file 1h.
        # Batch 1: 11 files (11h) -> Wait, 11+1 = 12h > 11.5h. So 11 files max.
        # Batch 2: 11 files (11h)
        # Batch 3: 2 files (2h)
        # Total 24 files.
        
        self.assertEqual(len(batches), 3)
        self.assertEqual(batches[0].total_parts, 3)
        self.assertEqual(len(batches[0].files), 11)
        self.assertEqual(len(batches[1].files), 11)
        self.assertEqual(len(batches[2].files), 2)
        print("Test Passed!")

if __name__ == '__main__':
    unittest.main()
