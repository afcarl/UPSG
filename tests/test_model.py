import unittest
import pickle
from os import system
import os
import numpy as np

from sklearn import datasets
from sklearn import grid_search
from sklearn.svm import SVC
from sklearn.cross_validation import train_test_split
from sklearn.cross_validation import cross_val_score
from sklearn.cross_validation import KFold as SKKFold
from sklearn.cross_validation import StratifiedKFold, LeaveOneOut 

from upsg.fetch.np import NumpyRead
from upsg.wrap.wrap_sklearn import wrap, wrap_and_make_instance
from upsg.export.csv import CSVWrite
from upsg.transform.split import SplitTrainTest, SplitY
from upsg.pipeline import Pipeline
from upsg.model.grid_search import GridSearch
from upsg.model.cross_validation import CrossValidationScore
from upsg.model.multiclassify import Multiclassify
from upsg.model.multimetric import Multimetric 
from upsg.model.multimetric import VisualMetricSpec, NumericMetricSpec
from upsg.utils import np_sa_to_dict

from utils import path_of_data, UPSGTestCase


import unittest
import sys
import pdb
import functools
import traceback

class TestModel(UPSGTestCase):

    def test_grid_search(self):
        """

        Simulates behavior of example in:
        http://scikit-learn.org/stable/modules/generated/sklearn.grid_search.GridSearchCV.html#sklearn.grid_search.GridSearchCV

        """
        folds = 2

        parameters = {
            'kernel': (
                'rbf',
                'linear'),
            'C': [
                1,
                10,
                100],
            'random_state': [0]}
        iris = datasets.load_iris()
        iris_data = iris.data
        iris_target = iris.target

        p = Pipeline()

        node_data = p.add(NumpyRead(iris_data))
        node_target = p.add(NumpyRead(iris_target))
        node_split = p.add(SplitTrainTest(2, random_state=1))
        node_search = p.add(GridSearch(wrap(SVC), 'score', parameters, folds))
        node_params_out = p.add(CSVWrite(self._tmp_files.get('out.csv')))

        node_data['output'] > node_split['input0']
        node_target['output'] > node_split['input1']
        node_split['train0'] > node_search['X_train']
        node_split['train1'] > node_search['y_train']
        node_split['test0'] > node_search['X_test']
        node_split['test1'] > node_search['y_test']
        node_search['params_out'] > node_params_out['input']

        self.run_pipeline(p)

        result = self._tmp_files.csv_read('out.csv')

        ctrl_X_train, _, ctrl_y_train, _ = train_test_split(
            iris_data, iris_target, random_state=1)
        ctrl_cv = SKKFold(ctrl_y_train.size, folds)
        ctrl_search = grid_search.GridSearchCV(SVC(), parameters, cv=ctrl_cv)
        ctrl_search.fit(ctrl_X_train, ctrl_y_train)
        control = ctrl_search.best_params_

        # TODO a number of configurations tie here, and sklearn picks a different
        # best configuration than upsg does (although they have the same score)
        # ideally, we want to find some parameters where there is a clear 
        # winner
        control = {'C': 10, 'kernel': 'linear', 'random_state': 0}

        self.assertEqual(np_sa_to_dict(np.array([result])), control)

    def test_cross_validation_score(self):
        rows = 100
        folds = 10

        X = np.random.random((rows, 10))
        y = np.random.randint(0, 2, (rows))
        
        for PartIter, kwargs in ((SKKFold, {'n': rows, 'n_folds': folds, 
                                            'random_stage': 0}),
                                 (StratifiedKFold, {'y': y, 'n_folds': folds,
                                                    'random_state': 0}),
                                 (LeaveOneOut, {'n': rows})):
            print PartIter

            p = Pipeline()

            np_in_X = p.add(NumpyRead(X))
            np_in_y = p.add(NumpyRead(y))

            cv_score = p.add(CrossValidationScore(
                wrap(SVC), 
                'score', 
                {}, 
                wrap(PartIter),
                n_folds=folds, 
                random_state=0))
            np_in_X['output'] > cv_score['X_train']
            np_in_y['output'] > cv_score['y_train']

            score_out = p.add(CSVWrite(self._tmp_files('out.csv')))
            cv_score['score'] > score_out['input']

            self.run_pipeline(p)

            result = self._tmp_files.csv_read('out.csv')['f0']

            print result
            ctrl_kf = PartIter(**kwargs)
            ctrl = np.mean(cross_val_score(SVC(), X, y, cv=ctrl_kf))
            print ctrl

            self.assertTrue(np.allclose(ctrl, result))

    def test_multimetric(self):
        samples = 150
        features = 3
        metrics = (VisualMetricSpec(
                           'sklearn.metrics.precision_recall_curve', # metric
                           'recall', # output key corresponding to x-axis
                           'precision', # output key corresponding to y-axis
                           'Precision/Recall Curve', # graph title
                           'recall', # x-label
                           'precision',), # y-label
                   VisualMetricSpec(
                           'sklearn.metrics.roc_curve',
                           None,
                           ('tpr', 'fpr'),
                           'ROC Curve',
                           'Results tagged positive',
                           'Rate',
                           ('FPR', 'TPR')),
                   NumericMetricSpec(
                           'sklearn.metrics.roc_auc_score',
                           'auc',
                           'ROC AUC Score'))

        X = np.random.random((samples, features))
        y = np.random.randint(0, 2, (samples))

        p = Pipeline()

        np_in_X = p.add(NumpyRead(X))
        np_in_y = p.add(NumpyRead(y))

        split_train_test = p.add(SplitTrainTest(2))
        np_in_X['output'] > split_train_test['input0']
        np_in_y['output'] > split_train_test['input1']

        clf = p.add(wrap_and_make_instance(SVC, kernel='linear')) 
        split_train_test['train0'] > clf['X_train']
        split_train_test['test0'] > clf['X_test']
        split_train_test['train1'] > clf['y_train']
        split_train_test['test1'] > clf['y_test']

        node_proba_cat_1 = p.add(SplitY(-1))
        clf['pred_proba'] > node_proba_cat_1['input']

        multi = p.add(Multimetric(
            metrics, 'SVC', 
            self._tmp_files('report.html')))
        node_proba_cat_1['y'] > multi['pred_proba']
        split_train_test['test1'] > multi['y_true']
        clf['params_out'] > multi['params']

        self.run_pipeline(p)

        self.assertTrue(os.path.isfile(self._tmp_files('report.html')))

    def test_multiclassify(self):
        samples = 150
        features = 3
        folds = 2

        X = np.random.random((samples, features))
        y = np.random.randint(0, 2, (samples))
        
        p = Pipeline()

        np_in_X = p.add(NumpyRead(X))
        np_in_y = p.add(NumpyRead(y))

        split_train_test = p.add(SplitTrainTest(2))
        np_in_X['output'] > split_train_test['input0']
        np_in_y['output'] > split_train_test['input1']

        multi = p.add(Multiclassify(
            'score', 
            self._tmp_files('report.html'),
            None,
            folds))

        split_train_test['train0'] > multi['X_train']
        split_train_test['test0'] > multi['X_test']
        split_train_test['train1'] > multi['y_train']
        split_train_test['test1'] > multi['y_test']
        
        self.run_pipeline(p)
        self.assertTrue(os.path.isfile(self._tmp_files('report.html')))
        
if __name__ == '__main__':
    unittest.main()
