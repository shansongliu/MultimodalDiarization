import numpy as np
from numpy.random import random
from sklearn.mixture import GaussianMixture, BayesianGaussianMixture
import pdb

class GMMComponents(object):
    """
    The Python interface to the components of a GMM.
    """
    def __init__(self, M, D, weights = None, means = None, covars = None):
        self.M = M
        self.D = D
        self.weights = weights if weights is not None else random(M)
        self.means = means if means is not None else  random((M,D))
        self.covars = covars if covars is not None else  random((M,D))
        self.comp_probs = np.empty(M, dtype=np.float32)
        
    def init_random_weights(self):
        self.weights = random((self.M))
        
    def init_random_means(self):
        self.means = random((self.M,self.D))

    def init_random_covars(self):
        self.covars = random((self.M, self.D, self.D))

    def shrink_components(self, new_M):
        self.weights = np.resize(self.weights, new_M)
        self.means = np.resize(self.means, new_M*self.D)
        self.covars = np.resize(self.covars, new_M*self.D*self.D)
            
class GMMEvalData(object):
    """
    The Python interface to the evaluation data generated by scoring a GMM.
    """
    def __init__(self, N, M):
        self.N = N
        self.M = M
        self.memberships = np.zeros((M,N), dtype=np.float32)
        self.loglikelihoods = np.zeros(N, dtype=np.float32)
        self.likelihood = 0.0

    def resize(self, N, M):
        self.memberships.resize((M,N))
        self.memberships = np.ascontiguousarray(self.memberships)
        self.loglikelihoods.resize(N, refcheck=False)
        self.loglikelihoods = np.ascontiguousarray(self.loglikelihoods)
        self.M = M
        self.N = N

class GMM(object):
    """
    The specialized GMM abstraction.
    """
    cvtype_name_list = ['diag','full'] #Types of covariance matrix
    def __init__(self, M, D, means=None, covars=None, weights=None, cvtype='diag'): 
        """
        cvtype must be one of 'diag' or 'full'. Uninitialized components will be seeded.
        """
        self.M = M
        self.D = D
        if cvtype in GMM.cvtype_name_list:
            self.cvtype = cvtype 
        else:
            raise RuntimeError("Specified cvtype is not allowed, try one of " + str(GMM.cvtype_name_list))

        self.components = GMMComponents(M, D, weights, means, covars)
        self.eval_data = GMMEvalData(1, M)
        self.clf = None # pure python mirror module

        if means is None and covars is None and weights is None:
            self.components_seeded = False
        else:
            self.components_seeded = True

    # Training and Evaluation of GMM
    def train_using_python(self, input_data, iters=10):
        seed = 5
        if self.components_seeded and self.clf is None:
            self.clf = GaussianMixture(n_components=self.M, covariance_type=self.cvtype, warm_start=True,\
                               max_iter=iters, init_params='random', random_state=seed, \
                               weights_init=self.components.weights, means_init=self.components.means, 
                               n_init=1)#, reg_covar=0.01)

        elif not self.components_seeded and self.clf is None:
            self.clf = GaussianMixture(n_components=self.M, covariance_type=self.cvtype, warm_start=True,\
                               max_iter=iters, init_params='random', n_init=1, random_state=seed)#, reg_covar=0.01)

        self.clf.fit(input_data)
        return self.clf.means_, self.clf.covariances_
    
    def train(self, input_data, min_em_iters=1, max_em_iters=10):
        """
        Train the GMM on the data. Optinally specify max and min iterations.
        """
        if input_data.shape[1] != self.D:
            print("Error: Data has %d features, model expects %d features." % (input_data.shape[1], self.D))
            
        self.components.means,self.components.covars = self.train_using_python(input_data, iters=max_em_iters)
        self.components.weights = self.clf.weights_

        self.eval_data.likelihood = self.clf.bic(input_data)
#        self.eval_data.likelihood = self.clf.score(input_data)
        
        return self.eval_data.likelihood

    def eval(self, obs_data):
        if obs_data.shape[1] != self.D:
            print("Error: Data has %d features, model expects %d features." % (obs_data.shape[1], self.D))

        self.eval_data.loglikelihoods = self.clf.score_samples(obs_data)
    
        logprob = self.eval_data.loglikelihoods
        self.eval_data.memberships = self.clf.predict_proba(obs_data)
        posteriors = self.eval_data.memberships
        return logprob, posteriors # N log probabilities, NxM posterior probabilities for each component

    def score(self, obs_data):
        logprob, posteriors = self.eval(obs_data)
        return logprob # N log probabilities

    def decode(self, obs_data):
        logprob, posteriors = self.eval(obs_data)
        return logprob, posteriors.argmax(axis=0) # N log probabilities, N indexes of most likely components 

    def predict(self, obs_data):
        logprob, posteriors = self.eval(obs_data)
        return posteriors.argmax(axis=0) # N indexes of most likely components
                            
#Functions for calculating distance between two GMMs according to BIC scores.
def compute_distance_BIC(gmm1, gmm2, data, em_iters=10):
    cd1_M = gmm1.M
    cd2_M = gmm2.M
    nComps = cd1_M + cd2_M

    ratio1 = float(cd1_M)/float(nComps)
    ratio2 = float(cd2_M)/float(nComps)

    w = np.ascontiguousarray(np.append(ratio1*gmm1.components.weights, ratio2*gmm2.components.weights))
    m = np.ascontiguousarray(np.append(gmm1.components.means, gmm2.components.means, axis=0))
    c = np.ascontiguousarray(np.append(gmm1.components.covars, gmm2.components.covars,axis=0))

    temp_GMM = GMM(nComps, gmm1.D, weights=w, means=m, covars=c, cvtype=gmm1.cvtype)
    temp_GMM.train(data, max_em_iters=em_iters)
#    score = temp_GMM.eval_data.likelihood - (gmm1.eval_data.likelihood + gmm2.eval_data.likelihood)
    #My update based on BIC    
    score = (gmm1.eval_data.likelihood + gmm2.eval_data.likelihood) - temp_GMM.eval_data.likelihood

    return temp_GMM, score