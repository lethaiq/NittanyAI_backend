"""
Jason Zhang 2018
jpz5181@ist.psu.edu
"""
import numpy as np
from scipy.sparse import csr_matrix
import cPickle
from Queue import Queue
import warnings
import difflib

from priorCourse import NNegLasso as model_grade
from grade_model import GradeModel as model_grade
from priorCourse import ind2onehot

class PathFinder(object):
    def __init__(self,
                 cou_name_dict_f="data/name_dict",
                 cou_desc_dict_f="data/cou_desc_dict",
                 graph_prerequisite_f="data/graph_prerequisite_sparse",
                 graph_prior_cou_f="data/graph_prior_cou_sparse",
                 graph_sub_mandatory_f="data/graph_sub_mandatory",
                 course_embds_f="data/embds"):

        with open(cou_name_dict_f, "r") as df:
            self.cou_name2id_dict, self.cou_id2name_dict = cPickle.load(df)
        with open(cou_desc_dict_f, "r") as df:
            self.cou_desc_dict = cPickle.load(df)
        with open(graph_prerequisite_f, "r") as df:
            self.graph_prerequisite, _ = cPickle.load(df)
        with open(graph_prior_cou_f, "r") as df:
            self.graph_prior = cPickle.load(df)
        with open(graph_sub_mandatory_f, "r") as df:
            self.graph_sub_mandatory = cPickle.load(df)     # not a graph actually
        with open(course_embds_f, "r") as df:
            self.embds = cPickle.load(df)

        self.C = len(self.cou_id2name_dict)
        self.N_sub = len(self.graph_sub_mandatory)
        self.sub_list = sorted(self.graph_sub_mandatory.keys())

        self.grade_model = self._grade_model_initial()

    ##################################################################################################################
    # id 2 name and vice versa #
    def cou_ind2name(self, ind):
        # from node index to course name #
        return self.cou_id2name_dict[ind]

    def cou_name2ind(self, name):
        return self.cou_name2id_dict[name]

    def sub_find(self, sub_name):
        if sub_name in self.graph_sub_mandatory:
            return sub_name
        else:
            sub_name_up = sub_name.upper()
            for cand in self.sub_list:
                if "(" + sub_name_up + ")" in cand:
                    return cand
        # not found #
        cand_list = difflib.get_close_matches(sub_name, self.sub_list, n=5)
        raise ValueError("sub_name: %s not found, did you mean %s?" % (sub_name, str(cand_list)))

    ##################################################################################################################

    ##################################################################################################################
    # in prerequisite_graph #
    def show_graph_prerequisite(self):
        return self.graph_prerequisite

    def path_finder_prerequisite(self, target_ind, source_inds=[],
                                 max_dependency=100, max_depth=100, weight_threshold=0.0, loop=True):
        """
        :param target_ind: target course index
        :param source_inds: source courses indices as list
        :param max_dependency: for each course, how many dependent courses will be chosen, if more than this, a warning
        is raised and largest max_dependency weights edges are used
        :param max_depth: for each subgraph, max depth it will reach, if reached, a warning is raised and subgraph is
        cut off
        :param weight_threshold: only consider edges with weight larger than weight_threshold
        :param loop: whether loop (cycle) is permitted, in test mode it is default as permitted
        :return: subgraph in csr_matrix
        """
        sub_graph = self._path_finder(target_ind, source_inds, self.graph_prerequisite,
                                      max_dependency=max_dependency, max_depth=max_depth,
                                      weight_threshold=weight_threshold, loop=loop)
        return sub_graph
    ##################################################################################################################

    ##################################################################################################################
    # in prior graph (performance graph) #
    def show_graph_prior(self):
        return self.graph_prior

    def path_finder_prior(self, target_ind, source_inds=[],
                          max_dependency=3, max_depth=3, weight_threshold=0.0, loop=True):
        """
        :param target_ind: target course index
        :param source_inds: source courses indices as list
        :param max_dependency: for each course, how many dependent courses will be chosen, if more than this, a warning
        is raised and largest max_dependency weights edges are used
        :param max_depth: for each subgraph, max depth it will reach, if reached, a warning is raised and subgraph is
        cut off
        :param weight_threshold: only consider edges with weight larger than weight_threshold
        :param loop: whether loop (cycle) is permitted, in test mode it is default as permitted
        :return: subgraph in csr_matrix
        """
        sub_graph = self._path_finder(target_ind, source_inds, self.graph_prior,
                                      max_dependency=max_dependency, max_depth=max_depth,
                                      weight_threshold=weight_threshold, loop=loop)
        return sub_graph

    def grade_estimate(self, target_ind, source_inds=[], course_grades=None):
        """
        predict target course grade given courses taken (current version only uses cou_taken without grades earned)
        :param target_ind: target course index
        :param source_inds: courses taken indices
        :return: grade in [0,1]
        """
        if course_grades is not None:
            assert len(source_inds) == len(course_grades)
        return self.grade_model.predict(target_ind, source_inds, course_grades)

    def top_courses(self, K=3, source_inds=[], course_grades=None, id_filter=None):
        """
        return top K courses in terms of estimated grades given source course grades
        :param K: top K
        :param source_inds: courses taken indices
        :param course_grades: course taken grades
        :param id_filter: callable function takes input as course_id, return bool, true for valid course, which can be returned as top_K
        :return: top_K_course_ids, top_K_course_grades
        """
        if course_grades is not None:
            assert len(source_inds) == len(course_grades)
        return self.grade_model.top_courses(K=K, input_ind=source_inds, input_grades=course_grades, id_filter=id_filter)
    #################################################################################################################

    #################################################################################################################
    # mandatory courses #
    def show_graph_sub_mandatory(self):
        return self.graph_sub_mandatory

    def show_mandatory_remain(self, sub, source_inds=[]):
        """
        return list of mandatory courses indices not taken yet
        :param sub: subject name of the query student
        :param source_inds: courses indices taken already
        :return: list of course index
        """
        sub = self.sub_find(sub)
        mandatory_total = self.graph_sub_mandatory[sub]
        mendatory_remain = list(set(mandatory_total) - set(source_inds))
        mendatory_remain.sort()
        return mendatory_remain
    #################################################################################################################

    #################################################################################################################
    # show course description #
    def course_description(self, cou_name):
        """
        :param cou_name: name of course (not course id)
        :return: course_description dictionary {
            "title":
            "description":
            "credits":
            "url":
        }
        """
        if cou_name not in self.cou_desc_dict:
            return None, None
        return self.cou_desc_dict[cou_name]

    #################################################################################################################
    # private functions #
    def _path_finder(self, target_ind, source_inds, graph,
                     max_dependency=100, max_depth=100, weight_threshold=0.0, loop=False):
        subgraph = {"data":[], "row":[], "col":[]}

        source_inds_set = set(source_inds)

        # BFS #
        BFS_queue_cur = Queue()
        BFS_queue_next = Queue()
        BFS_queue_cur.put(target_ind)
        nodes_seen_as_seed = set()               # check loop
        nodes_seen_as_seed_layer = set()         # check loop
        n_depth = 0
        while not BFS_queue_cur.empty() or not BFS_queue_next.empty():
            if BFS_queue_cur.empty():
                temp = BFS_queue_next
                BFS_queue_next = BFS_queue_cur
                BFS_queue_cur = temp
                nodes_seen_as_seed.union(nodes_seen_as_seed_layer)
                nodes_seen_as_seed_layer = set()
                n_depth += 1
                if n_depth >= max_depth:
                    warnings.warn("too deep path as max_depth=%d" % max_depth)
                    break
            seed_id = BFS_queue_cur.get()
            nodes_seen_as_seed_layer.add(seed_id)
            # check in source #
            if seed_id in source_inds_set:
                continue
            seed_edges = graph.getrow(seed_id)
            next_ids = np.array(seed_edges.indices, dtype=np.int32)
            next_weights = np.array(seed_edges.data, dtype=np.float64)
            # filter #
            next_ids, next_weights = self._loop_filter(next_ids, next_weights, nodes_seen_as_seed, loop)
            next_ids, next_weights = self._weight_filter(next_ids, next_weights, weight_threshold)
            next_ids, next_weights = self._max_dependency_filter(next_ids, next_weights, max_dependency)
            # add edges to subgraph #
            subgraph["data"] += next_weights.tolist()
            subgraph["row"] += [seed_id for i_ in range(next_ids.shape[0])]
            subgraph["col"] += next_ids.tolist()
            # add node to queue #
            for next_id in next_ids.tolist():
                BFS_queue_next.put(next_id)
        sub_graph = csr_matrix((subgraph["data"],(subgraph["row"], subgraph["col"])), [self.C, self.C])
        return sub_graph

    def _loop_filter(self, next_ids, next_weights, nodes_seen_as_seed, loop):
        if loop:
            # loop is permitted #
            return next_ids, next_weights
        else:
            inds = []
            for i_ in range(next_ids.shape[0]):
                ind = next_ids[i_]
                if ind in nodes_seen_as_seed:
                    warnings.warn("loop detected")
                else:
                    inds.append(ind)
            inds = np.array(inds)
            if len(inds.shape) == 0:
                inds = np.array([inds], dtype=np.int64)
            return next_ids[inds], next_weights[inds]

    def _weight_filter(self, next_ids, next_weights, weight_threshold):
        inds = np.argwhere(next_weights > weight_threshold).squeeze()
        if len(inds.shape) == 0:
            inds = np.array([inds], dtype=np.int64)
        return next_ids[inds], next_weights[inds]

    def _max_dependency_filter(self, next_ids, next_weights, max_dependency):
        n = next_ids.shape[0]
        if n <= max_dependency:
            return next_ids, next_weights
        else:
            warnings.warn("too many dependency as max_dependency=%d" % max_dependency)
            inds = np.argsort(next_weights)[:-max_dependency-1:-1]
            if len(inds.shape) == 0:
                inds = np.array([inds], dtype=np.int64)
            return next_ids[inds], next_weights[inds]

    # def _cou_ind2cid(self, ind):
    #     # from node index to course id #
    #     return self.cou_id_dict[ind]
    #
    # def _cou_cid2ind(self, cid):
    #     return self.cou_cid2id[cid]
    #
    # def _cou_cid2name(self, cid):
    #     # from course id to course name #
    #     return self.cou_id2name_dict[cid]

    def _dict_reverse(self, dictionary):
        dict_rev = {}
        for key in dictionary:
            value = dictionary[key]
            if value in dict_rev:
                warnings.warn("_dict_reverse applied to many-to-one dictionary")
            else:
                dict_rev[value] = key
        return dict_rev

    def _dict_transit(self, dictionary_p, dictionary_c):
        dict_transit = {}
        for key in dictionary_p:
            dict_transit[key] = dictionary_c[dictionary_p[key]]
        return dict_transit

    def _grade_model_initial(self):
        self.grade_model = model_grade(self.embds)
        return self.grade_model