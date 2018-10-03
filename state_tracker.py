from db_query import DBQuery
import numpy as np
from utils import convert_list_to_dict
from dialogue_config import all_intents, all_slots, usersim_default_key


class StateTracker:
    def __init__(self, database, constants):
        self.db_helper = DBQuery(database)
        self.match_key = usersim_default_key
        self.intents_dict = convert_list_to_dict(all_intents)
        self.num_intents = len(all_intents)
        self.slots_dict = convert_list_to_dict(all_slots)
        self.num_slots = len(all_slots)
        self.max_round_num = constants['run']['max_round_num']
        self.none_state = np.zeros(self.get_state_size())
        self.reset()

    def get_state_size(self):
        return 2 * self.num_intents + 7 * self.num_slots + 3 + self.max_round_num  # 224

    def reset(self):
        self.current_informs = {}
        self.history = []  # Is a list of the dialogues (dict) by the agent and user so far in the conversation
        self.round_num = 1

    def get_state(self, done=False):
        # If done then fill stat with zeros
        if done:
            return self.none_state

        user_action = self.history[-1]
        kb_results_dict = self.db_helper.get_db_results_for_slots(self.current_informs)
        last_agent_action = self.history[-2] if len(self.history) > 1 else None

        ########################################################################
        #   Create one-hot of acts to represent the current user action
        ########################################################################
        user_act_rep = np.zeros((1, self.num_intents))
        user_act_rep[0, self.intents_dict[user_action['intent']]] = 1.0

        ########################################################################
        #     Create bag of inform slots representation to represent the current user action
        ########################################################################
        user_inform_slots_rep = np.zeros((1, self.num_slots))
        for slot in user_action['inform_slots'].keys():
            user_inform_slots_rep[0, self.slots_dict[slot]] = 1.0

        ########################################################################
        #   Create bag of request slots representation to represent the current user action
        ########################################################################
        user_request_slots_rep = np.zeros((1, self.num_slots))
        for slot in user_action['request_slots'].keys():
            user_request_slots_rep[0, self.slots_dict[slot]] = 1.0

        ########################################################################
        #   Creat bag of filled_in slots based on the current_slots
        ########################################################################
        current_slots_rep = np.zeros((1, self.num_slots))
        for slot in self.current_informs:
            current_slots_rep[0, self.slots_dict[slot]] = 1.0

        ########################################################################
        #   Encode last agent act
        ########################################################################
        agent_act_rep = np.zeros((1, self.num_intents))
        if last_agent_action:
            agent_act_rep[0, self.intents_dict[last_agent_action['intent']]] = 1.0

        ########################################################################
        #   Encode last agent inform slots
        ########################################################################
        agent_inform_slots_rep = np.zeros((1, self.num_slots))
        if last_agent_action:
            for slot in last_agent_action['inform_slots'].keys():
                agent_inform_slots_rep[0, self.slots_dict[slot]] = 1.0

        ########################################################################
        #   Encode last agent request slots
        ########################################################################
        agent_request_slots_rep = np.zeros((1, self.num_slots))
        if last_agent_action:
            for slot in last_agent_action['request_slots'].keys():
                agent_request_slots_rep[0, self.slots_dict[slot]] = 1.0

        turn_rep = np.zeros((1, 1)) + self.round_num / 10.

        ########################################################################
        #  One-hot representation of the turn count?
        ########################################################################

        # Todo: I'm interested to see if including this increases performance

        turn_onehot_rep = np.zeros((1, self.max_round_num))
        turn_onehot_rep[0, self.round_num - 1] = 1.0

        ########################################################################
        #   Representation of KB results (scaled counts)
        ########################################################################
        kb_count_rep = np.zeros((1, self.num_slots + 1)) + kb_results_dict['matching_all_constraints'] / 100.
        for slot in kb_results_dict:
            if slot in self.slots_dict:
                kb_count_rep[0, self.slots_dict[slot]] = kb_results_dict[slot] / 100.

        ########################################################################
        #   Representation of KB results (binary)
        ########################################################################
        kb_binary_rep = np.zeros((1, self.num_slots + 1)) + np.sum(
            kb_results_dict['matching_all_constraints'] > 0.)
        for slot in kb_results_dict:
            if slot in self.slots_dict:
                kb_binary_rep[0, self.slots_dict[slot]] = np.sum(kb_results_dict[slot] > 0.)

        state_representation = np.hstack(
            [user_act_rep, user_inform_slots_rep, user_request_slots_rep, agent_act_rep, agent_inform_slots_rep,
             agent_request_slots_rep, current_slots_rep, turn_rep, turn_onehot_rep, kb_binary_rep, kb_count_rep]).flatten()
        return state_representation

    def update_state_agent(self, agent_action):
        # First check the informs (if there are any)
        inform_slots = self.db_helper.fill_inform_slots(agent_action['inform_slots'], self.current_informs)
        agent_action['inform_slots'] = inform_slots
        for key, value in agent_action['inform_slots'].items():
            assert key is not 'match_found'
            self.current_informs[key] = value  # add into inform_slots
        # Then check if the intent is match_found and fill the informs with the current informs from here
        if agent_action['intent'] is 'match_found':
            assert len(agent_action['inform_slots'].keys()) == 0, 'Cannot inform and have intent of match found!'
            agent_action['inform_slots'] = self.current_informs
            # Add a new inform slot to say whether there is actually a match (bool)
            db_results = self.db_helper.get_db_results(self.current_informs)
            # Note: SO this allows the agent to not have informed ticket yet to still check if it works
            agent_action['inform_slots'][self.match_key] = 'match available' if len(db_results) > 0 else 'no match available'
        self.history.append(agent_action)
        self.history[-1].update({'round': self.round_num, 'speaker': 'Agent'})
        self.round_num += 1
        # I may not tech. have to return agent_action, i think it updates anyway, but this is easier to read
        return agent_action, self.round_num

    def update_state_user(self, user_action):
        for key, value in user_action['inform_slots'].items():
            self.current_informs[key] = value
        self.history.append(user_action)
        # Todo: check if this still changes the user_action object, dont really want it to
        self.history[-1].update({'round': self.round_num, 'speaker': 'User'})
