# Importing necessary libraries
import json
from collections import defaultdict
import copy
from typing import Dict, List, Any, Tuple, Optional

# Threshold Values
ADAPTIVE_THRESHOLD_ENGLISH = 0.50
ADAPTIVE_THRESHOLD_MATH = 0.50

# Data Loading
def load_json_file(file_path: str) -> List[Dict[str, Any]]:
    try:
        with open(file_path, 'r') as f:
            data = json.load(f)
            if isinstance(data, list):
                return data
            else:
                print(f"Error: Unexpected JSON structure in {file_path}. Expected a list at root.")
                return []
    except FileNotFoundError:
        print(f"Error: File not found at {file_path}")
        return []
    except json.JSONDecodeError:
        print(f"Error: Could not decode JSON from {file_path}")
        return []

# Load all json data files
student_v2_data = load_json_file('67f2aae2c084263d16dbe462user_attempt_v2.json')
student_v3_data = load_json_file('66fece285a916f0bb5aea9c5user_attempt_v3.json')
raw_scoring_map = load_json_file('scoring_DSAT_v2.json')
scoring_map_processed: Dict[str, Any] = {}
for entry in raw_scoring_map:
    scoring_map_processed[entry["key"].lower()] = entry

# Data Processing and Scoring Functions
def group_attempts_by_subject_and_module(data: List[Dict[str, Any]]) -> Dict[str, Dict[str, List[Dict[str, Any]]]]:
    grouped = defaultdict(lambda: defaultdict(list))
    for item in data:
        subject = item["subject"]["name"].lower()
        complexity = item.get("compleixty", "").lower() # Use 'compleixty' field from data
        grouped[subject][complexity].append(item)
    return grouped

# Function to get scaled score
def get_scaled_score(subject_key: str, difficulty: str, raw_score: int, processed_scoring_map: Dict[str, Any]) -> int:
    subject_scoring_data = processed_scoring_map.get(subject_key.lower())
    if not subject_scoring_data:
        return 0
    score_map_list = subject_scoring_data.get("map", [])
    target_difficulty_key = difficulty.lower() 

    for entry in score_map_list:
        if entry["raw"] == raw_score:
            scaled_score = entry.get(target_difficulty_key)
            if scaled_score is not None:
                return scaled_score
            else:
                return 0 
    return 0

# Function to calculate current scores
def calculate_current_score(grouped_attempts: Dict[str, Dict[str, List[Dict[str, Any]]]], 
                            processed_scoring_map: Dict[str, Any],
                            adaptive_threshold_english: float, adaptive_threshold_math: float) -> Dict[str, Any]:
    total_overall_score = 0
    section_scores: Dict[str, Any] = {}
    
    for subject, complexities in grouped_attempts.items():
        easy_questions = complexities.get("easy", [])
        correct_easy_count = sum(1 for q in easy_questions if q.get("correct") == 1)
        total_easy_questions = len(easy_questions)

        current_module2_difficulty = "easy"
        if total_easy_questions > 0:
            performance_ratio = correct_easy_count / total_easy_questions
            threshold = adaptive_threshold_english if subject == "reading and writing" else adaptive_threshold_math
            if performance_ratio >= threshold:
                current_module2_difficulty = "hard"
        total_correct_in_subject = 0
        for comp_type, questions in complexities.items():
            total_correct_in_subject += sum(1 for q in questions if q.get("correct") == 1)
        scaled_score = get_scaled_score(
            subject_key=subject,
            difficulty=current_module2_difficulty,
            raw_score=total_correct_in_subject,
            processed_scoring_map=processed_scoring_map
        )
        
        section_scores[subject] = {
            "raw_score": total_correct_in_subject,
            "scaled_score": scaled_score,
            "module2_assigned_difficulty": current_module2_difficulty,
            "module1_correct": correct_easy_count,
            "module1_total": total_easy_questions
        }
        total_overall_score += scaled_score

    return {"total_score": total_overall_score, "sections": section_scores}

# Function for what if impact analysis
def what_if_impact_analysis(student_data: List[Dict[str, Any]], processed_scoring_map: Dict[str, Any],
                            adaptive_threshold_english: float, adaptive_threshold_math: float, 
                            debug_mode: bool = False) -> List[Dict[str, Any]]:
    original_grouped = group_attempts_by_subject_and_module(student_data)
    initial_score_info = calculate_current_score(original_grouped, processed_scoring_map,
                                                 adaptive_threshold_english, adaptive_threshold_math)
    initial_total_score = initial_score_info["total_score"]

    impact_results: List[Dict[str, Any]] = []
    all_incorrect_questions = [
        q for q in student_data if q.get("correct") == 0
    ]
    if not all_incorrect_questions and debug_mode:
        print("DEBUG: No incorrect questions found in the dataset. No recommendations possible.")
        return []
    for i, incorrect_q in enumerate(all_incorrect_questions):
        if debug_mode and i < 15:
            print(f"\n--- DEBUG: Simulating QID: {incorrect_q.get('question_id')} (Attempt ID: {incorrect_q.get('_id')}) ---")
            print(f"  Initial Total Score: {initial_total_score}")
            current_subject = incorrect_q['subject']['name'].lower()
            print(f"  Initial Section State ({current_subject}): {json.dumps(initial_score_info['sections'].get(current_subject), indent=2)}")
        simulated_student_data = copy.deepcopy(student_data)
        found_and_updated = False
        for q in simulated_student_data:
            if q.get("_id") == incorrect_q.get("_id"):
                q["correct"] = 1
                found_and_updated = True
                break
        if not found_and_updated:
            if debug_mode:
                print(f"DEBUG Warning: Could not find question {incorrect_q.get('question_id', incorrect_q.get('_id'))} to simulate as correct (by _id). Skipping simulation for this question).")
            continue
        simulated_grouped = group_attempts_by_subject_and_module(simulated_student_data)
        simulated_score_info = calculate_current_score(simulated_grouped, processed_scoring_map,
                                                       adaptive_threshold_english, adaptive_threshold_math)
        simulated_total_score = simulated_score_info["total_score"]
        score_impact = simulated_total_score - initial_total_score
        initial_subject_info = initial_score_info['sections'].get(current_subject, {})
        simulated_subject_info = simulated_score_info['sections'].get(current_subject, {})
        initial_m2_difficulty = initial_subject_info.get('module2_assigned_difficulty')
        simulated_m2_difficulty = simulated_subject_info.get('module2_assigned_difficulty')
        adaptive_impact_explanation = ""
        if incorrect_q.get('compleixty', '').lower() == 'easy' and initial_m2_difficulty != simulated_m2_difficulty:
            adaptive_impact_explanation = (
                f" (Adaptive Path Change: Module 2 difficulty changed from '{initial_m2_difficulty}' to '{simulated_m2_difficulty}')"
            )

        if debug_mode and i < 15:
            print(f"  Simulated Total Score: {simulated_total_score}")
            print(f"  Simulated Section State ({current_subject}): {json.dumps(simulated_score_info['sections'].get(current_subject), indent=2)}")
            print(f"  Calculated Score Impact: {score_impact}{adaptive_impact_explanation}")
            print("--------------------------------------------------")
        if score_impact > 0:
            impact_results.append({
                "question_id": incorrect_q.get("question_id"),
                "attempt_id": incorrect_q.get("_id"),
                "subject": incorrect_q["subject"]["name"],
                "complexity": incorrect_q["compleixty"],
                "score_impact": score_impact,
                "adaptive_impact_explanation": adaptive_impact_explanation,
                "initial_total_score": initial_total_score,
                "simulated_total_score": simulated_total_score,
                "initial_module2_difficulty": initial_m2_difficulty,
                "simulated_module2_difficulty": simulated_m2_difficulty
            })
    sorted_results = sorted(impact_results, key=lambda x: x['score_impact'], reverse=True)
    return sorted_results

# Main Analysis Execution
def analyze_student_performance(label: str, student_data: List[Dict[str, Any]], debug: bool = False):
    print(f"\n{'='*10} Analyzing {label} {'='*10}")
    grouped_data = group_attempts_by_subject_and_module(student_data)
    current_score_info = calculate_current_score(grouped_data, scoring_map_processed,
                                               ADAPTIVE_THRESHOLD_ENGLISH, ADAPTIVE_THRESHOLD_MATH)

    print("\nCurrent Score:")
    print(json.dumps(current_score_info, indent=2))
    recommendations = what_if_impact_analysis(student_data, scoring_map_processed,
                                              ADAPTIVE_THRESHOLD_ENGLISH, ADAPTIVE_THRESHOLD_MATH,
                                              debug_mode=debug)

    print(f"\n{'*'*5} Recommendations for {label} (Top 5) {'*'*5}")
    if not recommendations:
        print("No impactful recommendations found (This means all incorrect questions either led to 0 score change or there were no incorrect questions).")
    else:
        for i, rec in enumerate(recommendations[:5]):
            print(f"{i+1}. QID: {rec['question_id']} (Attempt ID: {rec['attempt_id']})")
            print(f"   Subject: {rec['subject']}, Complexity: {rec['complexity']}")
            print(f"   Potential Score Impact: +{rec['score_impact']} points{rec['adaptive_impact_explanation']}")
            print(f"   Initial Total Score: {rec['initial_total_score']}, Simulated Total Score: {rec['simulated_total_score']}")
            print(f"   Initial M2 Difficulty: {rec['initial_module2_difficulty']}, Simulated M2 Difficulty: {rec['simulated_module2_difficulty']}")
            print("-" * 30)
    print(f"\n{'='*40}")

if __name__ == "__main__":
    print("--- DSAT Adaptive Test Score Analysis and Recommendation System ---")
    print(f"Using Adaptive Thresholds: English={ADAPTIVE_THRESHOLD_ENGLISH}, Math={ADAPTIVE_THRESHOLD_MATH}")
    print("These thresholds determine Module 2 difficulty based on Module 1 performance.")
    analyze_student_performance("Student V2", student_v2_data, debug=True)
    analyze_student_performance("Student V3", student_v3_data, debug=True)