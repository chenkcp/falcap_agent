#!/usr/bin/env python3
"""Test the complete work order diagnostic flow."""

import sys
sys.path.insert(0, '.')

from app_ai_agent import bootstrap_agent

def main():
    print("=== Testing WorkOrder Diagnostic Flow ===\n")
    
    # Initialize agent
    print("1. Bootstrapping agent...")
    try:
        agent = bootstrap_agent()
        print("   [OK] Agent initialized\n")
    except Exception as e:
        print(f"   [FAIL] Failed to initialize agent: {e}\n")
        return False
    
    # Run diagnostic flow
    work_order = "4HDMORG260423D1"
    print(f"2. Running diagnostic for work order: {work_order}\n")
    try:
        # Manually step through the flow for debugging
        from agent.policy import AgentPolicy
        from agent.router import Router
        from prompts.system_prompt import SYSTEM_PROMPT
        
        policy = AgentPolicy()
        router = Router()
        tool_registry = agent.tool_registry
        
        wo = policy.validate_work_order_id(work_order)
        state = {
            "work_order_id": wo,
            "completed_tools": [],
            "explanations": [],
            "system_prompt": SYSTEM_PROMPT,
        }
        
        policy.validate_state(state)
        
        step = 0
        while True:
            tool_name = router.next_tool(state)
            
            if tool_name is None:
                print(f"   [OK] All tools completed")
                break
            
            step += 1
            print(f"   Step {step}: Running {tool_name}...")
            
            policy.validate_tool_name(tool_name)
            
            tool_fn = tool_registry[tool_name]
            print(f"      Tool function: {tool_fn}")
            
            result = tool_fn(state)
            print(f"      Result type: {type(result)}")
            
            if result is None:
                print(f"      [FAIL] Tool returned None!")
                return False
            
            state = result
            state["completed_tools"].append(tool_name)
        
        print(f"   [OK] Diagnostic completed\n")
        result = state
        
    except Exception as e:
        print(f"   [FAIL] Diagnostic failed: {e}\n")
        import traceback
        traceback.print_exc()
        return False
    
    # Show results
    print("3. Results Summary:")
    print(f"   Completed Tools ({len(result.get('completed_tools', []))}):") 
    for tool in result.get('completed_tools', []):
        print(f"     - {tool}")
    
    print(f"\n   Final Report Keys:")
    if result.get('final_report'):
        for key in sorted(result['final_report'].keys())[:15]:
            print(f"     - {key}")
    
    print("\n[OK] Complete flow validated successfully!\n")
    return True

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
