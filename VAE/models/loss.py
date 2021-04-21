
import torch
import torch.nn as nn
import torch.nn.functional as F
from torch.autograd import Variable
from torch.distributions.multinomial import Multinomial

import numpy as np

from torch import Tensor as T
import torch

import math

def VRBound(alpha,model,q_samples,q_mu, q_log_sigma,K=None,optimize_on='full_bound'):
		""" Monte-carlo estimate of variational renyi bound
		Args:
		    alpha (float): alpha of renyi alpha-divergence
		    model (VRalphaNet): net from models.network
		    q_samples (list): list of the output latent samples from training, with the (sampled) data as the first element.
		    	(i.e. should be the result of model.forward(data))
		    q_mu (list): output mu of network forward() method
		    q_log_sigma (list): resulting log_sigma output list of network forward() method  
		    K (int): # of importance samples. If None, use model approximation choice.
		    optimize_on (str, optional): 	"full_bound": sum over all samples inside log
		    								"sample": sample according to alpha importance weight
		    								"max": specifically VR-max
		
		"""
		# alpha = torch.float(alpha)
		if K is None:
			K=model.encoder.K

		# coerce to float
		alpha = float(alpha)

		prior_mu = Variable(torch.zeros_like(q_samples[-1]),requires_grad=False) # Prior is N(0,1) latent distribution in the ultimate encoder layer
		prior_log_sigma = Variable(torch.zeros_like(q_samples[-1]),requires_grad=False) # To work with innard of the LL function just use log(sigma^2) instead of sigma

		log_pq_ratio=gaussian_log_likelihood(q_samples[-1],(prior_mu,prior_log_sigma))
		#log_pq_ratio=torch.zeros_like(q_samples[-1].sum(axis=1))

		for current_sample, next_sample, qmu , qlog_sigma, p_layer in zip(q_samples,q_samples[1:],q_mu,q_log_sigma,model.decoder.layers[::-1]):
			p_out = next_sample
			for unit in p_layer:
				p_out, pmu, plog_sigma = unit.forward(p_out)
			
			if plog_sigma is not None:
				# then this unit is a stochastic gaussian decoder layer. want LL p(h_i | h_(i+1)) - LL q(h_(i+1) | h(i))
				log_pq_ratio+=gaussian_log_likelihood(current_sample,(pmu,plog_sigma)) - gaussian_log_likelihood(next_sample,(qmu,qlog_sigma))
			elif pmu is not None and plog_sigma is None:
				# then pmu is actually theta of a bernoulli distribution
				log_pq_ratio+=bernoulli_log_likelihood(current_sample,pmu) - gaussian_log_likelihood(next_sample,(qmu,qlog_sigma))

		# At this point log_pq_ratio is log(p(*)/q(*)) for each observation
		if abs(alpha-1)<=1e-3:
			# The optimize the ELBO! optimize_on doesn't matter in this case.
			return torch.sum(log_pq_ratio)/K

		elif optimize_on=='full_bound':
			log_pq_ratio = log_pq_ratio.reshape([-1,K]) * (1-alpha)
			log_pq_minus_max = log_pq_ratio - log_pq_ratio.max(axis=1,keepdim=True).values
			log_pq_sum = torch.log(torch.sum(torch.exp(log_pq_minus_max),axis=1,keepdim=True)/K)+log_pq_ratio.max(axis=1,keepdim=True).values
			return (1/(1-alpha))*torch.sum(log_pq_sum)

		elif optimize_on=="sample":
			log_pq_matrix = log_pq_ratio.reshape([-1, K]) * (1-alpha)
			log_pq_minus_max = log_pq_matrix - log_pq_matrix.max(axis=1, keepdim=True).values
			ws = torch.exp(log_pq_minus_max)
			ws_normalized = ws / torch.sum(ws, axis=1, keepdim=True)

			sample_dist = Multinomial(1,ws_normalized)
			log_pq_matrix = log_pq_matrix.gather(1,sample_dist.sample().argmax(1,keepdim=True))
			return (1/(1-alpha))*torch.sum(log_pq_matrix)

		elif optimize_on=='max':
			log_ws_matrix = log_pq_ratio.reshape([-1, K]) * (1-alpha)
			log_ws_matrix = log_ws_matrix.max(axis=1).values
			return (1/(1-alpha))*torch.sum(log_pq_matrix)
			

def gaussian_log_likelihood(sample,params):
	"""Calculate likelihood of current sample given previous (for encoder likelihood, talking about q(h_i | h_(i-1)))
	By switching sample position can just as easily be used for decoder (which would be p(h_(i-1) | h_i), since p operates forward in decreasing latent layers)
	
	Args:
	    sample: that generated by the network (or is just input!) whose likelihood we want to evaluate
	    params (tuple): mu and log_sigma generated by network given previous stochastic layer sample output
	
	
	Returns:
	    torch.Tensor: observation-length vector whose entries are Log Likelihood of sample given params
	"""
	(mu, log_sigma) = params

	sigma = torch.exp(log_sigma)
	output = -.5*sample.shape[1]*T.log(torch.tensor(2*np.pi)) -torch.sum(log_sigma,axis=1)- .5*torch.sum(torch.pow((sample-mu)/sigma,2),axis=1)
	return output

def bernoulli_log_likelihood(sample,theta):
	"""Calculate likelihood of current sample given previous (for encoder likelihood, talking about q(h_i | h_(i-1)))
	By switching sample position can just as easily be used for decoder (which would be p(h_(i-1) | h_i), since p operates forward in decreasing latent layers)
	
	Args:
	    sample: that generated by the network (or is just input!) whose likelihood we want to evaluate
	    theta (Tensor): output distribution-parametrizing 
	
	
	Returns:
	    torch.Tensor: observation-length vector whose entries are Log Likelihood of sample given params
	"""

	output = (1-sample)*torch.log(1-theta+1e-19) + sample*torch.log(theta+1e-19)

	return torch.sum(output,axis=1)
