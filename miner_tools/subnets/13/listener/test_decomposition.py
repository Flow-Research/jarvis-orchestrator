#!/usr/bin/env python3
"""
Test our decomposition algorithm with mock queries
"""

class TaskDecomposer:
    """SN13 Task Decomposition Logic"""
    
    CHUNK_THRESHOLD = 500  # Split if > 500 posts
    
    def decompose(self, bucket_id: dict, estimated_count: int = None) -> list:
        """
        Decide: Single operator or chunked?
        
        Returns list of tasks to dispatch to operators
        """
        count = estimated_count or 100
        
        print(f"\n📊 Analyzing task:")
        print(f"   Bucket: {bucket_id}")
        print(f"   Estimated count: {count}")
        
        # Decision: decompose?
        if count > self.CHUNK_THRESHOLD:
            print(f"   Decision: DECOMPOSE (count {count} > {self.CHUNK_THRESHOLD})")
            
            # Split into chunks
            chunks = []
            chunk_size = self.CHUNK_THRESHOLD
            
            for i in range(0, count, chunk_size):
                task = {
                    "task_id": f"task_{i // chunk_size}",
                    "subnet": 13,
                    "operator_type": f"{bucket_id['source'].lower()}_scraper",
                    "params": {
                        **bucket_id,
                        "range_start": i,
                        "range_end": min(i + chunk_size, count)
                    },
                    "estimated_posts": min(chunk_size, count - i)
                }
                chunks.append(task)
                print(f"   📦 Chunk {i // chunk_size}: posts {i}-{min(i+chunk_size, count)}")
            
            return chunks
            
        else:
            print(f"   Decision: SINGLE OPERATOR (count {count} <= {self.CHUNK_THRESHOLD})")
            return [{
                "task_id": "task_0",
                "subnet": 13,
                "operator_type": f"{bucket_id['source'].lower()}_scraper",
                "params": bucket_id,
                "estimated_posts": count
            }]


def test_scenarios():
    """Test different scenarios"""
    decomposer = TaskDecomposer()
    
    print("="*70)
    print("🧪 TESTING SN13 TASK DECOMPOSITION")
    print("="*70)
    
    # Scenario 1: Large bucket (>500)
    print("\n\n" + "="*50)
    print("SCENARIO 1: Large request (1500 posts)")
    print("="*50)
    bucket1 = {"source": "X", "label": "$BTC", "time_bucket_id": 1845}
    tasks1 = decomposer.decompose(bucket1, estimated_count=1500)
    print(f"\n✅ Created {len(tasks1)} tasks")
    
    # Scenario 2: Medium bucket (300)
    print("\n\n" + "="*50)
    print("SCENARIO 2: Medium request (300 posts)")
    print("="*50)
    bucket2 = {"source": "X", "label": "$ETH", "time_bucket_id": 1845}
    tasks2 = decomposer.decompose(bucket2, estimated_count=300)
    print(f"\n✅ Created {len(tasks2)} tasks")
    
    # Scenario 3: Small bucket (50)
    print("\n\n" + "="*50)
    print("SCENARIO 3: Small request (50 posts)")
    print("="*50)
    bucket3 = {"source": "REDDIT", "label": "bittensor", "time_bucket_id": 1845}
    tasks3 = decomposer.decompose(bucket3, estimated_count=50)
    print(f"\n✅ Created {len(tasks3)} tasks")
    
    # Scenario 4: Reddit large
    print("\n\n" + "="*50)
    print("SCENARIO 4: Reddit large (2000 posts)")
    print("="*50)
    bucket4 = {"source": "REDDIT", "label": "AI", "time_bucket_id": 1850}
    tasks4 = decomposer.decompose(bucket4, estimated_count=2000)
    print(f"\n✅ Created {len(tasks4)} tasks")
    
    print("\n\n" + "="*70)
    print("📋 SUMMARY")
    print("="*70)
    print(f"Scenario 1 (1500 posts): {len(tasks1)} chunks")
    print(f"Scenario 2 (300 posts): {len(tasks2)} chunks")  
    print(f"Scenario 3 (50 posts): {len(tasks3)} chunks")
    print(f"Scenario 4 (2000 posts): {len(tasks4)} chunks")


if __name__ == "__main__":
    test_scenarios()
