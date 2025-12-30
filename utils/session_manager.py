import streamlit as st

def init_session_state():
    '''세션 상태 초기화'''
    if 'page' not in st.session_state:
        st.session_state['page'] = "description"
    if 'keywords' not in st.session_state:
        st.session_state.keywords = []
    if 'test_results_a' not in st.session_state:
        st.session_state.test_results_a = []
    if 'test_results_b' not in st.session_state:
        st.session_state.test_results_b = []
    if 'step_1_completed' not in st.session_state:
        st.session_state.step_1_completed = False
    if 'step_2a_completed' not in st.session_state:
        st.session_state.step_2a_completed = False
    if 'step_2b_completed' not in st.session_state:
        st.session_state.step_2b_completed = False

def get_keywords():
    '''저장된 키워드 반환'''
    return st.session_state.get('keywords', [])

def set_keywords(keywords):
    '''키워드 저장'''
    st.session_state.keywords = keywords
    st.session_state.step_1_completed = len(keywords) > 0

def is_step_completed(step):
    '''단계 완료 여부 확인'''
    return st.session_state.get(f'step_{step}_completed', False)

def set_step_completed(step, completed=True):
    '''단계 완료 상태 설정'''
    st.session_state[f'step_{step}_completed'] = completed

def get_test_results(system):
    '''테스트 결과 반환'''
    key = f'test_results_{system.lower()}'
    return st.session_state.get(key, [])

def set_test_results(system, results):
    '''테스트 결과 저장'''
    key = f'test_results_{system.lower()}'
    st.session_state[key] = results