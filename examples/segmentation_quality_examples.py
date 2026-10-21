"""
Example script showing how to use the Segmentation Quality Database
and VLM Analysis Processor with TreeAIBox

This demonstrates:
1. Processing VLM analysis results
2. Querying flagged trees
3. Recording re-segmentation attempts
4. Generating reports
"""

import json
import sys
import os
from datetime import datetime

# Add modules to path
sys.path.insert(0, os.path.dirname(__file__))

from modules.segmentation_quality_db import SegmentationQualityDB, detect_multiple_trees
from modules.vlm_analysis_processor import VLMAnalysisProcessor


def example_1_process_vlm_analysis():
    """Example 1: Process a VLM analysis result"""
    print("\n" + "="*60)
    print("EXAMPLE 1: Processing VLM Analysis Result")
    print("="*60)
    
    # Initialize processor
    processor = VLMAnalysisProcessor()
    
    # Simulate a VLM response indicating multiple trees
    vlm_response = {
        "is_tree": "yes",
        "appears_to_be_noise": "no",
        "tree_type": "deciduous",
        "trunk_well_defined": "no",
        "trunk_disconnected": "yes",
        "total_trunks_detected": 2,
        "crown_shape_quality": "poor",
        "analysis_summary": "Two distinct deciduous trees detected. Trunks are separate with different branching patterns."
    }
    
    # Process the analysis
    flagged_tree_id = processor.process_analysis_result(
        tree_id=42,
        file_path="/data/forest_plot_001.las",
        point_count=85432,
        analysis_id="20250417_150000",
        vlm_response=json.dumps(vlm_response),
        screenshots_dir="/logs/analysis_001"
    )
    
    if flagged_tree_id:
        print(f"✓ Tree flagged successfully!")
        print(f"  Database ID: {flagged_tree_id}")
        print(f"  Tree ID: 42")
        print(f"  Issue: Multiple trees detected (2)")
        print(f"  File: /data/forest_plot_001.las")
    
    processor.close()


def example_2_query_flagged_trees():
    """Example 2: Query flagged trees from database"""
    print("\n" + "="*60)
    print("EXAMPLE 2: Querying Flagged Trees")
    print("="*60)
    
    processor = VLMAnalysisProcessor()
    
    # Get trees flagged with multiple trees detected
    print("\nFetching trees flagged for re-segmentation...")
    trees = processor.get_trees_needing_resegmentation(
        issue_type='multiple_trees',
        limit=10
    )
    
    if trees:
        print(f"\nFound {len(trees)} trees needing re-segmentation:\n")
        for tree in trees:
            print(f"  Tree ID: {tree['tree_id']}")
            print(f"    Points: {tree['point_count']}")
            print(f"    Crowns Detected: {tree.get('num_distinct_crowns', 1)}")
            print(f"    Detected: {tree['detected_on']}")
            print(f"    Status: {tree['resolution_status']}")
            print(f"    Summary: {tree.get('analysis_summary', 'N/A')[:60]}...")
            print()
    else:
        print("No flagged trees found.")
    
    processor.close()


def example_3_statistics():
    """Example 3: Get database statistics"""
    print("\n" + "="*60)
    print("EXAMPLE 3: Database Statistics")
    print("="*60)
    
    processor = VLMAnalysisProcessor()
    
    stats = processor.get_database_statistics()
    
    print(f"\nDatabase Statistics:")
    print(f"  Total Flagged Trees: {stats.get('total_flagged_trees', 0)}")
    print(f"  Multiple Trees Detected: {stats.get('multiple_trees_detected', 0)}")
    print(f"  Pending Resolution: {stats.get('pending', 0)}")
    print(f"  Resolved: {stats.get('resolved', 0)}")
    
    if 'issue_distribution' in stats:
        print(f"\nIssue Distribution:")
        for issue_type, count in stats['issue_distribution'].items():
            print(f"  {issue_type}: {count}")
    
    processor.close()


def example_4_mark_resegmentation():
    """Example 4: Record successful re-segmentation"""
    print("\n" + "="*60)
    print("EXAMPLE 4: Recording Re-segmentation Success")
    print("="*60)
    
    processor = VLMAnalysisProcessor()
    
    # Assume we have flagged_tree_id = 1
    # This would be from a previous analysis
    flagged_tree_id = 1
    
    print(f"\nRecording re-segmentation for tree ID {flagged_tree_id}...")
    
    processor.mark_resegmentation_complete(
        flagged_tree_id=flagged_tree_id,
        num_segments_created=2,
        segment_ids=[42, 43],
        method='Multi-trunk isolation with adaptive clustering'
    )
    
    print("✓ Re-segmentation recorded successfully!")
    print("  2 segments created: 42, 43")
    print("  Tree marked as 'resolved'")
    
    processor.close()


def example_5_export_report():
    """Example 5: Export database to JSON report"""
    print("\n" + "="*60)
    print("EXAMPLE 5: Exporting Report")
    print("="*60)
    
    processor = VLMAnalysisProcessor()
    
    report_path = os.path.join(
        os.path.dirname(__file__),
        f"segmentation_quality_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    )
    
    print(f"\nExporting database to: {report_path}")
    
    if processor.export_report(report_path):
        print(f"✓ Report exported successfully!")
        
        # Show file size
        file_size = os.path.getsize(report_path)
        print(f"  File size: {file_size:,} bytes")
        
        # Show preview of report
        with open(report_path, 'r') as f:
            data = json.load(f)
            print(f"\nReport Contents:")
            print(f"  Export Timestamp: {data.get('export_timestamp')}")
            print(f"  Total Trees in Report: {len(data.get('flagged_trees', []))}")
            if data.get('statistics'):
                print(f"  Statistics: {data['statistics']}")
    else:
        print("✗ Failed to export report")
    
    processor.close()


def example_6_detect_multiple_trees():
    """Example 6: Test multiple tree detection logic"""
    print("\n" + "="*60)
    print("EXAMPLE 6: Testing Multiple Tree Detection")
    print("="*60)
    
    # Test cases
    test_cases = [
        {
            "name": "Clear multiple trees (2 trunks)",
            "response": {
                "tree_type": "deciduous",
                "trunk_well_defined": "no",
                "trunk_disconnected": "yes",
                "total_trunks_detected": 2,
                "analysis_summary": "Two distinct trees detected"
            }
        },
        {
            "name": "Single well-defined tree",
            "response": {
                "tree_type": "coniferous",
                "trunk_well_defined": "yes",
                "trunk_disconnected": "no",
                "total_trunks_detected": 1,
                "analysis_summary": "Single coniferous tree with good segmentation"
            }
        },
        {
            "name": "Multiple trees from summary",
            "response": {
                "tree_type": "deciduous",
                "trunk_well_defined": "no",
                "trunk_disconnected": "yes",
                "total_trunks_detected": 1,
                "analysis_summary": "Multiple deciduous trees detected in segment, approximately 3 separate crowns"
            }
        }
    ]
    
    print()
    for test in test_cases:
        is_multiple, num_trees = detect_multiple_trees(test['response'])
        status = "🚩 MULTIPLE" if is_multiple else "✓ SINGLE"
        print(f"{status} | {test['name']}")
        if is_multiple:
            print(f"       └─ {num_trees} distinct trees/crowns detected")
        print()


def example_7_workflow():
    """Example 7: Complete workflow from analysis to report"""
    print("\n" + "="*60)
    print("EXAMPLE 7: Complete Workflow")
    print("="*60)
    
    processor = VLMAnalysisProcessor()
    
    print("\nStep 1: Analyze multiple trees and store to database")
    
    # Simulate analyzing 3 trees
    analyses = [
        {
            "tree_id": 101,
            "file": "/data/plot_1.las",
            "points": 45000,
            "response": {
                "is_tree": "yes",
                "total_trunks_detected": 2,
                "analysis_summary": "Two trees in one segment"
            }
        },
        {
            "tree_id": 102,
            "file": "/data/plot_1.las",
            "points": 38000,
            "response": {
                "is_tree": "yes",
                "total_trunks_detected": 1,
                "analysis_summary": "Good quality single tree"
            }
        },
        {
            "tree_id": 103,
            "file": "/data/plot_1.las",
            "points": 52000,
            "response": {
                "is_tree": "yes",
                "total_trunks_detected": 3,
                "analysis_summary": "Three distinct trees detected"
            }
        }
    ]
    
    for i, analysis in enumerate(analyses, 1):
        flagged_id = processor.process_analysis_result(
            tree_id=analysis['tree_id'],
            file_path=analysis['file'],
            point_count=analysis['points'],
            analysis_id=f"workflow_{i}",
            vlm_response=json.dumps(analysis['response'])
        )
        if flagged_id:
            print(f"  ✓ Tree {analysis['tree_id']}: Flagged (ID: {flagged_id})")
        else:
            print(f"  ✓ Tree {analysis['tree_id']}: Passed checks")
    
    print("\nStep 2: Query problematic trees")
    trees = processor.get_trees_needing_resegmentation('multiple_trees', limit=10)
    print(f"  Found {len(trees)} trees needing re-segmentation")
    
    print("\nStep 3: Show statistics")
    stats = processor.get_database_statistics()
    print(f"  Total flagged: {stats.get('total_flagged_trees', 0)}")
    print(f"  Multiple trees: {stats.get('multiple_trees_detected', 0)}")
    print(f"  Pending: {stats.get('pending', 0)}")
    print(f"  Resolved: {stats.get('resolved', 0)}")
    
    print("\nStep 4: Export report")
    report_path = os.path.join(
        os.path.dirname(__file__),
        "workflow_report.json"
    )
    if processor.export_report(report_path):
        print(f"  ✓ Report exported to {os.path.basename(report_path)}")
    
    processor.close()


def main():
    """Run all examples"""
    print("\n" + "#"*60)
    print("# Segmentation Quality Database - Usage Examples")
    print("#"*60)
    
    try:
        example_1_process_vlm_analysis()
        example_2_query_flagged_trees()
        example_3_statistics()
        example_4_mark_resegmentation()
        example_5_export_report()
        example_6_detect_multiple_trees()
        example_7_workflow()
        
        print("\n" + "#"*60)
        print("# All examples completed successfully!")
        print("#"*60 + "\n")
        
    except Exception as e:
        print(f"\n✗ Error running examples: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
