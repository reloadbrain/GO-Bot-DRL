import random
from dialogue_config import usersim_default_key, FAIL, NO_OUTCOME, SUCCESS, usersim_required_init_inform_keys
import constants
import random

'''

So I am going to chaneg this around once i make sure it works first. I will be adding 'check_match_found' as an agent
intent, and make this the ONLY way to inform match. This will serve as the agent figuring out if EVEYTHING (not just 
constraint checking) is good. Response to done will mainly just be a final check but not have much else. 

Also I will be getting rid of 'thanks' probably

'''


class UserSimulator:
    def __init__(self, goal_list):
        self.goal_list = goal_list
        self.max_round = constants['run']['max_round_num']
        # This is eqivalent to ticket in the moviedatabase, it MUST be in req of user sim goal
        self.default_key = usersim_default_key
        # A list of REQUIRED to be in the first action inform keys
        self.init_informs = usersim_required_init_inform_keys

    def reset(self):
        self.goal = random.choice(self.goal_list)
        # Add default slot to requests of goal
        self.goal['request_slots'][self.default_key] = 'UNK'
        self.state = {}
        # Add all inform slots informed by agent or usersim to this dict
        self.state['history_slots'] = {}
        # Any inform slots for the current usersim action, empty at start of turn
        self.state['inform_slots'] = {}
        # Current request slots the usersim wants to request
        self.state['request_slots'] = {}
        # Init. all informs and requests in user goal, remove slots as informs made by user or agent
        self.state['rest_slots'] = {}
        # Rest slots is going to be a dict of all goal informs and requests
        self.state['rest_slots'].update(self.goal['inform_slots'])
        self.state['rest_slots'].update(self.goal['request_slots'])
        self.state['intent'] = ''
        # False for failure, true for success, auto init to failure
        self.constraint_check = FAIL

        return self._return_init_action()

    def _return_init_action(self):
        # Always request
        self.state['intent'] = 'request'

        if self.goal['inform_slots']:
            # So pick all the required init informs, and add if they exist in goal inform slots
            for inform_key in self.init_informs:
                if inform_key in self.goal['inform_slots']:
                    self.state['inform_slots'][inform_key] = self.goal['inform_slots'][inform_key]
                    self.state['rest_slots'].remove(inform_key)
            # If nothing was added then pick a random one to add
            if not self.state['inform_slots']:
                key, value = random.choice(list(self.goal['inform_slots'].items()))
                self.state['inform_slots'][key] = value
                self.state['rest_slots'].remove(key)

        # Now add a request, do a random one if something other than ticket available
        def_in = self.goal['request_slots'].pop(self.default_key, False)
        if self.goal['request_slots']:
            req_key = random.choice(list(self.goal['request_slots'].keys()))
        else:
            req_key = self.default_key
        if def_in:
            assert def_in is 'UNK'
            self.goal['request_slots'][req_key] = 'UNK'

        user_response = {}
        user_response['intent'] = self.state['intent']
        user_response['request_slots'] = self.state['request_slots']
        user_response['inform_slots'] = self.state['inform_slots']

        return user_response

    def step(self, agent_action, round_num):
        # Add all inform slots just informed to history slots and Clear all state inform slots (just sent out)
        self.state['history_slots'].update(self.state['inform_slots'])
        self.state['inform_slots'].clear()

        done = False
        succ = NO_OUTCOME
        # First check round num, if past max then fail
        if round_num > self.max_round:
            done = True
            succ = False
            self.state['intent'] = 'done'
            self.state['request_slots'].clear()
        else:
            agent_intent = agent_action['intent']
            if agent_intent == 'request':
                self.response_to_request(agent_action)
            if agent_intent == 'inform':
                self.response_to_inform(agent_action)
            if agent_intent == 'match_found':
                self.response_to_match_found(agent_action)
            if agent_intent == 'done':
                succ = self.response_to_done(agent_action)
                self.state['intent'] = 'done'
                self.state['request_slots'].clear()
                done = True

        # My assumptions:
        # If request intent, then make sure request slots
        if self.state['intent'] is 'request':
            assert self.state['request_slots']
        # If inform intent, then make sure inform slots and NO request slots
        if self.state['intent'] is 'inform':
            assert self.state['inform_slots']
            assert not self.state['request_slots']

        user_response = {}
        user_response['intent'] = self.state['intent']
        user_response['request_slots'] = self.state['request_slots']
        user_response['inform_slots'] = self.state['inform_slots']

        reward = self._reward_function(succ)

        return user_response, reward, done, succ

    def _reward_function(self, succ):
        if succ == FAIL:
            reward = -self.max_round
        elif succ == SUCCESS:
            reward = 2*self.max_round
        else:
            reward = -1
        return reward

    def response_to_request(self, agent_action):
        agent_request_key = agent_action['request_slots'].keys()[0]
        # First Case: if agent requests for something that is in the usersims goal inform slots, then inform it
        if agent_request_key in self.goal['inform_slots']:
            self.state['intent'] = 'inform'
            self.state['inform_slots'][agent_request_key] = self.goal['inform_slots'][agent_request_key]
            self.state['request_slots'].clear()
            self.state['rest_slots'].pop(agent_request_key, None)
        # Second Case: if the agent requests for something in usersims goal request slots and it has already been
        # informed, then inform it
        elif agent_request_key in self.goal['request_slots'] and agent_request_key in self.state['history_slots']:
            self.state['intent'] = 'inform'
            self.state['inform_slots'][agent_request_key] = self.state['history_slots'][agent_request_key]
            self.state['request_slots'].clear()
        # Third Case: if the agent requests for something in the usersims goal request slots and it HASN'T been
        # informed, then request it with all available inform slots left for usersim to inform
        elif agent_request_key in self.goal['request_slots'] and agent_request_key in self.state['rest_slots']:
            self.state['intent'] = 'request'
            self.state['request_slots'][agent_request_key] = 'UNK'
            # Todo: So i dont really like this, fuck around with it and see if there is a better option that still works
            for (key, value) in self.state['rest_slots']:
                # Means it is an inform
                if value is not 'UNK':
                    self.state['inform_slots'][key] = value
                    self.state['rest_slots'].pop(key)
        # Fourth and Final Case: otherwise the usersim does not care about the slot being requested, then inform
        # Todo: So this is the way i want this, but its different than theirs, so change if its fucking shit up
        else:
            self.state['intent'] = 'inform'
            self.state['inform_slots'][agent_request_key] = 'anything'
            self.state['request_slots'].clear()


    def response_to_inform(self, agent_action):
        agent_inform_key = agent_action['inform_slots'].keys()[0]
        agent_inform_value = agent_action['inform_slots'][agent_inform_key]

        # Add all informs (by agent too) to hist slots
        self.state['history_slots'][agent_inform_key] = agent_inform_value
        # Remove from rest slots if in it
        self.state['rest_slots'].pop(agent_inform_key, None)
        # Remove from request slots if in it
        self.state['request_slots'].pop(agent_inform_key, None)

        # First Case: If agent informs something that is in goal informs and the value it informed doesnt match, then inform the correct value
        if agent_inform_value is not self.goal['inform_slots'].get(agent_inform_key, agent_inform_value):
            self.state['intent'] = 'inform'
            self.state['inform_slots'][agent_inform_key] = self.goal['inform_slots'][agent_inform_key]
            self.state['request_slots'].clear()
        # Second Case: Otherwise pick a random action to take
        else:
            # - If anything in state requests then request it
            if self.state['request_slots']:
                self.state['intent'] = 'request'
            # - Else if something to say in rest slots, pick something
            elif self.state['rest_slots']:
                # Will return False if not in rest slots, and the value of 'UNK' if it is
                def_in = self.state['rest_slots'].pop(self.default_key, False)
                if self.state['rest_slots']:
                    key, value = random.choice(list(self.state['rest_slots'].items()))
                    if value is not 'UNK':
                        self.state['intent'] = 'inform'
                        self.state['inform_slots'][key] = value
                        self.state['rest_slots'].pop(key)
                    else:
                        self.state['intent'] = 'request'
                        self.state['request_slots'][key] = 'UNK'
                else:
                    self.state['intent'] = 'request'
                    self.state['request_slots'][self.default_key] = 'UNK'
                # If it was in, then add it back because it can only be removed from an inform
                if def_in:
                    assert def_in is 'UNK'
                    self.state['rest_slots'][self.default_key] = 'UNK'
            # - Otherwise respond with 'nothing to say' intent
            else:
                # TOdo: probably will change
                # Note: This thanks will actually have no requests
                self.state['intent'] = 'thanks'

    # All ST informs will be sent in with this agent action
    def response_to_match_found(self, agent_action):
        agent_informs = agent_action['inform_slots']

        # Todo: I will be changing this intent to 'accept' and clearing requests
        # Note: keep in mind for now 'thanks' can have requests
        self.state['intent'] = 'thanks'
        self.constraint_check = SUCCESS

        # Todo: In mine, remove this clase and instead add match to hist (remove from req and rest) no matter what
        if agent_informs[self.default_key] == 'no match available':
            self.state['history_slots'][self.default_key] = 'no match available'
            if self.default_key in self.state['rest_slots']: self.state['rest_slots'].remove(self.default_key)
            if self.default_key in self.state['request_slots'].keys(): del self.state['request_slots'][self.default_key]

        # Check to see if all goal informs are in the agent informs, and that the values match
        for (key, value) in self.goal['inform_slots'].items():
            assert value is not None
            # Will return true if key not in agent informs OR if value does not match value of agent informs[key]
            if value != agent_informs.get(key, None):
                self.state['intent'] = 'reject'
                self.state['request_slots'].clear()
                self.constraint_check = FAIL

    def response_to_done(self, agent_action):
        # Case 1: Check constraits from match found
        if self.constraint_check == FAIL:
            return FAIL

        # Case 2: Check if requests and rests empty
        # Todo: So they remove the ticket slot before see if rest are empty... idk why, if it doesnt affect performance then remove this
        # Will return False if not in rest slots, and the value of 'UNK' if it is
        # Assumption is if the rests are empty then so are the requests
        if not self.state['rest_slots']:
            assert not self.state['request_slots']
        def_in = self.state['rest_slots'].pop(self.default_key, False)
        if self.state['rest_slots']:
            if def_in:
                assert def_in is 'UNK'
                self.state['rest_slots'][self.default_key] = 'UNK'
            return FAIL

        # Case 3: Check if hist slots contain any NO VALUE MATCH
        # Todo: Will be changing this, all i care about is that any GOAL INFORM is in the hist slots, and those are matches
        for info_slot in self.state['history_slots'].keys():
            # if any no value match in constraints then fail
            if self.state['history_slots'][info_slot] == 'no match available':
                return FAIL
            if info_slot in self.goal['inform_slots'].keys():
                # If informs given by agent/history do not match the goal contraints then fail
                if self.state['history_slots'][info_slot] != self.goal['inform_slots'][info_slot]:
                    return FAIL


        return SUCCESS